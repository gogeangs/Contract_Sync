"""AI 챗봇 서비스 — 3차 개발 S1-3 ~ S1-7

Gemini 기반 질의 처리 + DB 데이터 조회 + 권한 분리 + SSE 스트리밍
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import (
    User, Team, TeamMember, Project, Task, Client,
    Notification, ActivityLog, PaymentSchedule,
    ChatSession, ChatMessage,
)

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# ── 프롬프트 인젝션 방어 패턴 (P-1 §1.5) ──
_INJECTION_PATTERNS = [
    r"시스템\s*프롬프트를?\s*(무시|알려|보여|출력)",
    r"(ignore|disregard|forget)\s*(your|the|all)\s*(instructions|prompt|rules)",
    r"(reveal|show|print|output)\s*(your|the|system)\s*(prompt|instructions)",
    r"역할을?\s*(바꿔|변경|무시)",
    r"지시를?\s*(알려|보여)",
    r"you\s*are\s*now",
    r"act\s*as\s*(if|a|an)",
    r"pretend\s*(to\s*be|you)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

# ── 빠른 질문 프리셋 (P-2) ──
QUICK_PRESETS = {
    "common": [
        {"id": 1, "text": "내 미완료 업무", "query": "나에게 할당된 미완료 업무 목록을 보여줘", "icon": "📋"},
        {"id": 2, "text": "진행 중 프로젝트", "query": "현재 진행 중인 프로젝트 목록과 진행률을 보여줘", "icon": "📊"},
        {"id": 3, "text": "이번 주 마감 업무", "query": "이번 주 내 마감인 업무를 알려줘", "icon": "⏰"},
        {"id": 4, "text": "읽지 않은 알림", "query": "읽지 않은 알림을 요약해줘", "icon": "🔔"},
        {"id": 5, "text": "오늘의 업무 요약", "query": "오늘 내가 해야 할 업무를 정리해줘", "icon": "📌"},
    ],
    "pm": [
        {"id": 6, "text": "고객 피드백 대기 현황", "query": "피드백 대기 중인 프로젝트와 대기 일수를 알려줘"},
        {"id": 7, "text": "이번 달 프로젝트 일정", "query": "이번 달 시작/마감 예정인 프로젝트 목록"},
        {"id": 8, "text": "팀 업무량 현황", "query": "팀원별 현재 할당된 업무 수와 상태를 보여줘"},
    ],
    "designer": [
        {"id": 9, "text": "내 디자인 업무 현황", "query": "나에게 할당된 디자인 단계 업무 목록"},
        {"id": 10, "text": "수정 요청 목록", "query": "고객 수정 요청(revision_requested) 상태인 업무"},
    ],
    "developer": [
        {"id": 11, "text": "개발 대기 업무", "query": "디자인 완료 → 개발 대기 상태인 업무 목록"},
        {"id": 12, "text": "내 진행 중 업무", "query": "나에게 할당된 in_progress 상태 업무"},
    ],
    "admin": [
        {"id": 13, "text": "미수금 현황", "query": "미수금(overdue + pending) 총액과 프로젝트별 내역"},
        {"id": 14, "text": "이번 달 매출 요약", "query": "이번 달 수금 완료 금액과 예정 금액"},
        {"id": 15, "text": "전체 프로젝트 현황", "query": "상태별 프로젝트 수 + 지연 프로젝트 목록"},
    ],
}

# ── 시스템 프롬프트 (P-1 §1.3) ──
SYSTEM_PROMPT_TEMPLATE = """당신은 Contract Sync의 내부 업무 어시스턴트입니다.
이름은 "CS 어시스턴트"이며, 회사 내부 직원들의 업무를 보조합니다.

## 역할
- Contract Sync 시스템의 데이터를 조회하고 요약하여 답변합니다.
- 읽기 전용입니다. 데이터를 생성, 수정, 삭제할 수 없습니다.
- 시스템에 존재하는 데이터만 기반으로 답변하며, 추측하지 않습니다.

## 응답 규칙
1. 한국어로 답변합니다. 사용자가 영어로 질문하면 영어로 답변합니다.
2. 간결하고 명확하게 답변합니다. 불필요한 서론을 붙이지 않습니다.
3. 숫자, 날짜, 상태 등 구체적인 정보를 포함합니다.
4. 3개 이상의 항목은 목록 또는 표로 정리합니다.
5. 데이터가 없으면 "해당 데이터가 없습니다"라고 안내합니다.
6. 모르는 내용은 "확인할 수 없습니다"라고 솔직하게 답변합니다.

## 사용자 정보
- 이름: {user_name}
- 역할: {user_role}
- 소속 팀: {team_names}

## 권한
{permission_context}

## 금지 행동
- 시스템에 없는 데이터를 만들어내지 않습니다.
- 개인정보(비밀번호, 토큰 등)를 노출하지 않습니다.
- 데이터 수정/삭제 방법을 안내하지 않습니다 (읽기 전용).
- 회사 외부 정보에 대해 답변하지 않습니다.
- 다른 직원의 급여, 인사 정보에 대해 답변하지 않습니다.
- 시스템 내부 구조(DB 스키마, API 엔드포인트 등)를 노출하지 않습니다.
"""


# ══════════════════════════════════════════
#  권한 분리 (S1-5, P-3)
# ══════════════════════════════════════════

# 금액 관련 차단 필드 (P-3 §3.6)
_MONEY_FIELDS = {"contract_amount", "amount", "paid_amount", "total_amount", "unit_price"}


async def get_user_team_roles(db: AsyncSession, user_id: int) -> list[dict]:
    """사용자의 팀 멤버십과 역할 조회"""
    result = await db.execute(
        select(TeamMember, Team.name).join(Team, Team.id == TeamMember.team_id)
        .where(TeamMember.user_id == user_id)
    )
    return [{"team_id": tm.team_id, "team_name": name, "role": tm.role}
            for tm, name in result.all()]


async def is_admin_user(db: AsyncSession, user_id: int) -> bool:
    """사용자가 owner 역할을 가진 팀이 있는지 확인"""
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.user_id == user_id,
            TeamMember.role == "owner",
        )
    )
    return result.scalar_one_or_none() is not None


async def build_permission_context(db: AsyncSession, user: User) -> str:
    """권한 컨텍스트 문자열 생성 (P-3 §3.2)"""
    if await is_admin_user(db, user.id):
        return "조회 가능: 모든 데이터 (수금/매출/미수금 포함)"
    return (
        "조회 가능: 발주처, 프로젝트, 업무, 댓글, 활동 로그, 보고서, 팀 업무량, 본인 알림\n"
        "조회 불가: 수금/결제 정보, 매출/미수금 통계, 견적서 금액\n"
        "수금 관련 질문 시: '수금 정보는 관리자만 조회할 수 있습니다.'로 응답"
    )


async def build_system_prompt(db: AsyncSession, user: User) -> str:
    """사용자 맞춤 시스템 프롬프트 빌드"""
    team_roles = await get_user_team_roles(db, user.id)
    team_names = ", ".join(tr["team_name"] for tr in team_roles) or "없음"
    roles = set(tr["role"] for tr in team_roles)
    user_role = "관리자" if "owner" in roles else ("운영자" if "admin" in roles else "팀원")
    permission_context = await build_permission_context(db, user)

    return SYSTEM_PROMPT_TEMPLATE.format(
        user_name=user.name or user.email,
        user_role=user_role,
        team_names=team_names,
        permission_context=permission_context,
    )


def check_prompt_injection(message: str) -> bool:
    """프롬프트 인젝션 시도 감지 (P-1 §1.5)"""
    return bool(_INJECTION_RE.search(message))


# ══════════════════════════════════════════
#  데이터 조회 함수 (S1-4)
# ══════════════════════════════════════════

async def get_user_team_ids(db: AsyncSession, user_id: int) -> list[int]:
    result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user_id)
    )
    return [r[0] for r in result.all()]


async def get_user_projects(db: AsyncSession, user_id: int, team_ids: list[int]) -> list[dict]:
    """소속 팀의 active/planning 프로젝트"""
    from app.services.common import access_filter
    result = await db.execute(
        select(Project).where(
            access_filter(Project, user_id, team_ids),
            Project.status.in_(["active", "planning"]),
        ).order_by(Project.updated_at.desc()).limit(20)
    )
    projects = result.scalars().all()
    return [{"id": p.id, "project_name": p.project_name, "status": p.status,
             "start_date": p.start_date, "end_date": p.end_date,
             "client_id": p.client_id} for p in projects]


async def get_user_tasks(db: AsyncSession, user_id: int) -> list[dict]:
    """본인 assignee의 미완료 업무"""
    result = await db.execute(
        select(Task, Project.project_name).outerjoin(Project, Task.project_id == Project.id)
        .where(Task.assignee_id == user_id, Task.status.notin_(["completed", "confirmed"]))
        .order_by(Task.due_date.asc()).limit(30)
    )
    return [{"id": t.id, "title": t.task_name, "priority": t.priority,
             "status": t.status, "deadline": t.due_date,
             "project_name": pn or "독립 업무"} for t, pn in result.all()]


async def get_weekly_deadline_tasks(db: AsyncSession, user_id: int) -> list[dict]:
    """이번 주 마감 업무"""
    now_kst = datetime.now(KST)
    week_start = now_kst.strftime("%Y-%m-%d")
    # 이번 주 일요일
    week_end = (now_kst + timedelta(days=(6 - now_kst.weekday()))).strftime("%Y-%m-%d")

    result = await db.execute(
        select(Task, Project.project_name).outerjoin(Project, Task.project_id == Project.id)
        .where(
            Task.assignee_id == user_id,
            Task.due_date >= week_start,
            Task.due_date <= week_end,
            Task.status.notin_(["completed", "confirmed"]),
        ).order_by(Task.due_date.asc())
    )
    return [{"id": t.id, "title": t.task_name, "deadline": t.due_date,
             "project_name": pn or "독립 업무",
             "days_left": (datetime.strptime(t.due_date, "%Y-%m-%d").date() - now_kst.date()).days if t.due_date else None}
            for t, pn in result.all()]


async def get_user_notifications(db: AsyncSession, user_id: int, unread_only: bool = False) -> list[dict]:
    """본인 알림"""
    q = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        q = q.where(Notification.is_read == False)  # noqa: E712
    q = q.order_by(Notification.created_at.desc()).limit(20)
    result = await db.execute(q)
    return [{"id": n.id, "type": n.type, "title": n.title,
             "message": n.message, "is_read": n.is_read,
             "created_at": n.created_at.isoformat() if n.created_at else None}
            for n in result.scalars().all()]


async def get_project_activities(db: AsyncSession, project_id: int) -> list[dict]:
    """프로젝트의 최근 활동 로그 (최대 20개)"""
    result = await db.execute(
        select(ActivityLog, User.name).join(User, User.id == ActivityLog.user_id)
        .where(ActivityLog.project_id == project_id)
        .order_by(ActivityLog.created_at.desc()).limit(20)
    )
    return [{"user_name": name or "알 수 없음", "action": al.action,
             "target_type": al.target_type, "target_name": al.target_name,
             "detail": al.detail,
             "created_at": al.created_at.isoformat() if al.created_at else None}
            for al, name in result.all()]


async def get_team_workload(db: AsyncSession, team_ids: list[int]) -> list[dict]:
    """팀원별 업무량"""
    if not team_ids:
        return []
    result = await db.execute(
        select(
            User.name,
            func.count(Task.id).label("total"),
            func.sum(func.iif(Task.status == "completed", 1, 0)).label("completed"),
            func.sum(func.iif(Task.status == "in_progress", 1, 0)).label("in_progress"),
        ).join(Task, Task.assignee_id == User.id)
        .where(Task.team_id.in_(team_ids))
        .group_by(User.id)
    )
    return [{"user_name": name, "assigned_count": total,
             "completed_count": completed or 0, "in_progress_count": ip or 0}
            for name, total, completed, ip in result.all()]


async def get_project_summary(db: AsyncSession, project_id: int) -> dict | None:
    """프로젝트 전체 현황 요약"""
    project = await db.get(Project, project_id)
    if not project:
        return None

    # 업무 통계
    task_result = await db.execute(
        select(
            func.count(Task.id),
            func.sum(func.iif(Task.status == "completed", 1, 0)),
            func.sum(func.iif(Task.status == "in_progress", 1, 0)),
        ).where(Task.project_id == project_id)
    )
    total, completed, in_progress = task_result.one()

    # 발주처 이름
    client_name = None
    if project.client_id:
        client = await db.get(Client, project.client_id)
        client_name = client.name if client else None

    return {
        "name": project.project_name,
        "client": client_name,
        "status": project.status,
        "start_date": project.start_date,
        "end_date": project.end_date,
        "task_total": total or 0,
        "task_completed": completed or 0,
        "task_in_progress": in_progress or 0,
    }


async def get_overdue_payments(db: AsyncSession) -> dict:
    """미수금 현황 (관리자용)"""
    result = await db.execute(
        select(PaymentSchedule, Project.project_name)
        .join(Project, Project.id == PaymentSchedule.project_id)
        .where(PaymentSchedule.status.in_(["overdue", "pending"]))
    )
    total = 0
    by_project = []
    for ps, pname in result.all():
        total += ps.amount or 0
        by_project.append({
            "project_name": pname,
            "amount": ps.amount,
            "status": ps.status,
            "due_date": ps.due_date,
        })
    return {"total": total, "by_project": by_project}


async def get_monthly_revenue(db: AsyncSession, year: int, month: int) -> dict:
    """월별 매출 (관리자용)"""
    month_prefix = f"{year}-{month:02d}"
    result = await db.execute(
        select(PaymentSchedule, Project.project_name)
        .join(Project, Project.id == PaymentSchedule.project_id)
        .where(PaymentSchedule.due_date.like(f"{month_prefix}%"))
    )
    paid_total = 0
    pending_total = 0
    for ps, _ in result.all():
        if ps.status == "paid":
            paid_total += ps.paid_amount or ps.amount or 0
        else:
            pending_total += ps.amount or 0
    return {"paid_total": paid_total, "pending_total": pending_total, "month": month_prefix}


async def get_all_project_status(db: AsyncSession, team_ids: list[int]) -> dict:
    """전체 프로젝트 현황 (관리자용)"""
    from app.services.common import access_filter
    result = await db.execute(
        select(Project.status, func.count(Project.id))
        .where(access_filter(Project, 0, team_ids))  # team-wide
        .group_by(Project.status)
    )
    by_status = {status: count for status, count in result.all()}
    return {"by_status": by_status, "total": sum(by_status.values())}


# ══════════════════════════════════════════
#  데이터 컨텍스트 빌드 (Gemini에 전달)
# ══════════════════════════════════════════

async def build_data_context(db: AsyncSession, user: User, message: str) -> str:
    """사용자 질문에 관련된 데이터를 조회하여 컨텍스트 문자열로 반환"""
    team_ids = await get_user_team_ids(db, user.id)
    admin = await is_admin_user(db, user.id)
    msg_lower = message.lower()

    sections = []

    # 키워드 기반 데이터 조회
    if any(k in msg_lower for k in ["업무", "할일", "할 일", "task", "todo", "미완료"]):
        tasks = await get_user_tasks(db, user.id)
        if tasks:
            sections.append(f"[사용자의 미완료 업무 ({len(tasks)}건)]\n" + json.dumps(tasks, ensure_ascii=False, indent=2))

    if any(k in msg_lower for k in ["마감", "이번 주", "deadline", "이번주"]):
        deadline_tasks = await get_weekly_deadline_tasks(db, user.id)
        if deadline_tasks:
            sections.append(f"[이번 주 마감 업무 ({len(deadline_tasks)}건)]\n" + json.dumps(deadline_tasks, ensure_ascii=False, indent=2))

    if any(k in msg_lower for k in ["프로젝트", "project", "진행 중", "진행중"]):
        projects = await get_user_projects(db, user.id, team_ids)
        if projects:
            sections.append(f"[진행 중 프로젝트 ({len(projects)}건)]\n" + json.dumps(projects, ensure_ascii=False, indent=2))

    if any(k in msg_lower for k in ["알림", "notification", "읽지 않은"]):
        notifs = await get_user_notifications(db, user.id, unread_only=True)
        sections.append(f"[읽지 않은 알림 ({len(notifs)}건)]\n" + json.dumps(notifs, ensure_ascii=False, indent=2))

    if any(k in msg_lower for k in ["팀", "업무량", "workload", "팀원"]):
        workload = await get_team_workload(db, team_ids)
        if workload:
            sections.append("[팀 업무량]\n" + json.dumps(workload, ensure_ascii=False, indent=2))

    if any(k in msg_lower for k in ["오늘", "today", "요약"]):
        tasks = await get_user_tasks(db, user.id)
        deadline_tasks = await get_weekly_deadline_tasks(db, user.id)
        notifs = await get_user_notifications(db, user.id, unread_only=True)
        sections.append(f"[오늘의 요약]\n- 미완료 업무: {len(tasks)}건\n- 이번 주 마감: {len(deadline_tasks)}건\n- 읽지 않은 알림: {len(notifs)}건")

    # 관리자 전용 데이터
    if admin:
        if any(k in msg_lower for k in ["미수금", "overdue", "수금", "결제"]):
            payments = await get_overdue_payments(db)
            sections.append("[미수금 현황]\n" + json.dumps(payments, ensure_ascii=False, indent=2))

        if any(k in msg_lower for k in ["매출", "revenue", "이번 달", "이번달"]):
            now_kst = datetime.now(KST)
            revenue = await get_monthly_revenue(db, now_kst.year, now_kst.month)
            sections.append("[이번 달 매출]\n" + json.dumps(revenue, ensure_ascii=False, indent=2))

        if any(k in msg_lower for k in ["전체 프로젝트", "현황", "status"]):
            status = await get_all_project_status(db, team_ids)
            sections.append("[전체 프로젝트 현황]\n" + json.dumps(status, ensure_ascii=False, indent=2))
    else:
        # 비관리자가 금액 관련 질의 시 차단 컨텍스트
        if any(k in msg_lower for k in ["미수금", "수금", "매출", "결제", "금액", "계약금", "잔금"]):
            sections.append("[권한 차단] 수금/결제/매출 정보는 관리자만 조회할 수 있습니다.")

    # 특정 프로젝트 언급 시 요약 제공
    # "A 프로젝트" 패턴 매칭
    project_match = re.search(r'["\']?(.+?)["\']?\s*프로젝트', message)
    if project_match:
        pname = project_match.group(1).strip()
        from app.services.common import access_filter
        result = await db.execute(
            select(Project).where(
                access_filter(Project, user.id, team_ids),
                Project.project_name.contains(pname),
            ).limit(1)
        )
        project = result.scalar_one_or_none()
        if project:
            summary = await get_project_summary(db, project.id)
            if summary:
                sections.append(f"[프로젝트 상세: {pname}]\n" + json.dumps(summary, ensure_ascii=False, indent=2))
            activities = await get_project_activities(db, project.id)
            if activities:
                sections.append("[최근 활동 (최대 20건)]\n" + json.dumps(activities[:10], ensure_ascii=False, indent=2))

    if not sections:
        # 기본: 업무 + 프로젝트 요약 제공
        tasks = await get_user_tasks(db, user.id)
        projects = await get_user_projects(db, user.id, team_ids)
        sections.append(f"[사용자 업무 ({len(tasks)}건)]\n" + json.dumps(tasks[:10], ensure_ascii=False, indent=2))
        sections.append(f"[진행 중 프로젝트 ({len(projects)}건)]\n" + json.dumps(projects[:5], ensure_ascii=False, indent=2))

    return "\n\n".join(sections)


# ══════════════════════════════════════════
#  Gemini 스트리밍 호출 (S1-7)
# ══════════════════════════════════════════

async def stream_chatbot_response(
    db: AsyncSession,
    user: User,
    message: str,
    session_id: int | None = None,
) -> AsyncGenerator[str, None]:
    """챗봇 응답을 SSE 이벤트 문자열로 스트리밍

    Yields: SSE 형식 문자열 ("event: token\ndata: {...}\n\n")
    """
    # 프롬프트 인젝션 체크
    if check_prompt_injection(message):
        error_msg = "죄송합니다. 해당 요청은 처리할 수 없습니다."
        yield f'event: error\ndata: {json.dumps({"error": error_msg}, ensure_ascii=False)}\n\n'
        return

    # 세션 관리
    if session_id:
        chat_session = await db.get(ChatSession, session_id)
        if not chat_session or chat_session.user_id != user.id:
            chat_session = None
    else:
        chat_session = None

    if not chat_session:
        chat_session = ChatSession(user_id=user.id, title=message[:100])
        db.add(chat_session)
        await db.flush()

    # 사용자 메시지 저장
    user_msg = ChatMessage(
        chat_session_id=chat_session.id,
        message_type="user",
        content=message,
    )
    db.add(user_msg)
    await db.flush()

    # 시스템 프롬프트 + 데이터 컨텍스트 빌드
    system_prompt = await build_system_prompt(db, user)
    data_context = await build_data_context(db, user, message)

    # 이전 대화 이력 (최근 10개)
    history_result = await db.execute(
        select(ChatMessage).where(ChatMessage.chat_session_id == chat_session.id)
        .order_by(ChatMessage.created_at.desc()).limit(10)
    )
    history_msgs = list(reversed(history_result.scalars().all()))

    # Gemini 호출
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)

        # 대화 이력 구성
        contents = []
        for msg in history_msgs[:-1]:  # 현재 메시지 제외
            role = "user" if msg.message_type == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg.content)]))

        # 현재 메시지 + 데이터 컨텍스트
        current_text = f"{message}\n\n--- 시스템 데이터 (사용자에게 직접 보이지 않음) ---\n{data_context}"
        contents.append(types.Content(role="user", parts=[types.Part(text=current_text)]))

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.3,
        )

        full_content = ""
        response = client.models.generate_content_stream(
            model="gemini-2.0-flash",
            contents=contents,
            config=config,
        )

        for chunk in response:
            if chunk.text:
                delta = chunk.text
                full_content += delta
                data = json.dumps({"content": full_content, "delta": delta}, ensure_ascii=False)
                yield f'event: token\ndata: {data}\n\n'

        # AI 응답 저장
        ai_msg = ChatMessage(
            chat_session_id=chat_session.id,
            message_type="assistant",
            content=full_content,
        )
        db.add(ai_msg)

        # 세션 제목 업데이트 (첫 응답이면)
        if len(history_msgs) <= 1:
            chat_session.title = message[:100]

        await db.commit()

        done_data = json.dumps({
            "message_id": ai_msg.id,
            "session_id": chat_session.id,
            "full_content": full_content,
        }, ensure_ascii=False)
        yield f'event: done\ndata: {done_data}\n\n'

    except Exception as e:
        logger.error(f"챗봇 Gemini 호출 실패: {e}")
        await db.rollback()
        error_data = json.dumps({"error": f"AI 응답 생성 중 오류가 발생했습니다: {str(e)}"}, ensure_ascii=False)
        yield f'event: error\ndata: {error_data}\n\n'


# ══════════════════════════════════════════
#  대화 이력 조회
# ══════════════════════════════════════════

async def get_chat_history(
    db: AsyncSession,
    user_id: int,
    session_id: int | None = None,
    limit: int = 50,
) -> dict:
    """대화 이력 조회"""
    if session_id:
        chat_session = await db.get(ChatSession, session_id)
        if not chat_session or chat_session.user_id != user_id:
            return {"sessions": []}
        sessions = [chat_session]
    else:
        result = await db.execute(
            select(ChatSession).where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc()).limit(limit)
        )
        sessions = result.scalars().all()

    output = []
    for s in sessions:
        msg_result = await db.execute(
            select(ChatMessage).where(ChatMessage.chat_session_id == s.id)
            .order_by(ChatMessage.created_at.asc()).limit(100)
        )
        messages = msg_result.scalars().all()
        output.append({
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "messages": [{
                "id": m.id,
                "message_type": m.message_type,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            } for m in messages],
        })
    return {"sessions": output}


async def delete_chat_session(db: AsyncSession, user_id: int, session_id: int) -> bool:
    """대화 세션 삭제"""
    chat_session = await db.get(ChatSession, session_id)
    if not chat_session or chat_session.user_id != user_id:
        return False
    await db.delete(chat_session)
    await db.commit()
    return True


def get_presets_for_user(team_roles: list[dict]) -> list[dict]:
    """사용자 역할에 맞는 빠른 질문 프리셋 반환 (최대 6개)"""
    roles = set(tr["role"] for tr in team_roles)
    presets = QUICK_PRESETS["common"][:3]  # 공통 3개

    if "owner" in roles:
        presets += QUICK_PRESETS["admin"][:3]
    elif any(tr.get("role") in ("admin", "member") for tr in team_roles):
        presets += QUICK_PRESETS["pm"][:3]
    else:
        presets += QUICK_PRESETS["developer"][:3]

    return presets[:6]
