"""대시보드 서비스 — Phase 7 (§18) + 6차 브리핑

통계 요약, 매출 추이, 팀 워크로드, AI 인사이트, 오늘의 브리핑.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    Project, Task, PaymentSchedule, User, utc_now,
    Notification, Attendance, TeamMember,
)
from app.services.common import get_user_team_ids, access_filter

KST = timezone(timedelta(hours=9))

logger = logging.getLogger(__name__)


# ── 1. 대시보드 통계 (6개 카드) ──

async def get_summary(db: AsyncSession, user) -> dict:
    """대시보드 통계 카드 6개"""
    team_ids = await get_user_team_ids(db, user.id)

    # 활성 프로젝트
    active_result = await db.execute(
        select(func.count(Project.id)).where(
            access_filter(Project, user.id, team_ids),
            Project.status == "active",
        )
    )
    active_projects = active_result.scalar() or 0

    # 대기 업무
    pending_result = await db.execute(
        select(func.count(Task.id)).where(
            access_filter(Task, user.id, team_ids),
            Task.status == "pending",
        )
    )
    pending_tasks = pending_result.scalar() or 0

    # 진행 중 업무
    in_progress_result = await db.execute(
        select(func.count(Task.id)).where(
            access_filter(Task, user.id, team_ids),
            Task.status == "in_progress",
        )
    )
    in_progress_tasks = in_progress_result.scalar() or 0

    # 피드백 대기 업무
    fb_result = await db.execute(
        select(func.count(Task.id)).where(
            access_filter(Task, user.id, team_ids),
            Task.status == "feedback_pending",
        )
    )
    feedback_pending_tasks = fb_result.scalar() or 0

    # 이번 달 수금액
    now = utc_now()
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    month_end = now.strftime("%Y-%m-%d")

    monthly_rev_result = await db.execute(
        select(func.coalesce(func.sum(PaymentSchedule.paid_amount), 0)).where(
            PaymentSchedule.status == "paid",
            PaymentSchedule.paid_date >= month_start,
            PaymentSchedule.paid_date <= month_end,
        )
    )
    monthly_revenue = monthly_rev_result.scalar() or 0

    # 미수금 (pending + invoiced + overdue)
    outstanding_result = await db.execute(
        select(func.coalesce(func.sum(PaymentSchedule.amount), 0)).where(
            PaymentSchedule.status.in_(["pending", "invoiced", "overdue"]),
        )
    )
    outstanding_amount = outstanding_result.scalar() or 0

    return {
        "active_projects": active_projects,
        "pending_tasks": pending_tasks,
        "in_progress_tasks": in_progress_tasks,
        "monthly_revenue": int(monthly_revenue),
        "outstanding_amount": int(outstanding_amount),
        "feedback_pending_tasks": feedback_pending_tasks,
    }


# ── 2. 매출 추이 (최근 6개월) ──

async def get_revenue(db: AsyncSession, user) -> dict:
    """최근 6개월 매출 추이"""
    now = utc_now()
    months = []
    amounts = []

    for i in range(5, -1, -1):
        # i개월 전
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        month_str = f"{year}-{month:02d}"
        months.append(month_str)

        # 해당 월 수금 합계
        result = await db.execute(
            select(func.coalesce(func.sum(PaymentSchedule.paid_amount), 0)).where(
                PaymentSchedule.status == "paid",
                PaymentSchedule.paid_date.like(f"{month_str}%"),
            )
        )
        amounts.append(int(result.scalar() or 0))

    return {"months": months, "amounts": amounts}


# ── 3. 팀 워크로드 ──

async def get_workload(db: AsyncSession, user) -> list[dict]:
    """팀원별 업무 건수 + 완료 건수"""
    team_ids = await get_user_team_ids(db, user.id)
    if not team_ids:
        # 개인 사용자 — 본인만
        result = await db.execute(
            select(
                Task.assignee_id,
                func.count(Task.id).label("task_count"),
                func.sum(case(
                    (Task.status.in_(["completed", "confirmed"]), 1),
                    else_=0,
                )).label("completed_count"),
            ).where(
                Task.assignee_id == user.id,
            ).group_by(Task.assignee_id)
        )
    else:
        # 팀원 전체
        result = await db.execute(
            select(
                Task.assignee_id,
                func.count(Task.id).label("task_count"),
                func.sum(case(
                    (Task.status.in_(["completed", "confirmed"]), 1),
                    else_=0,
                )).label("completed_count"),
            ).where(
                Task.team_id.in_(team_ids),
                Task.assignee_id != None,  # noqa: E711
            ).group_by(Task.assignee_id)
        )

    rows = result.all()
    workload = []
    for row in rows:
        assignee = await db.get(User, row.assignee_id)
        if assignee:
            workload.append({
                "user_id": row.assignee_id,
                "user_name": assignee.name,
                "task_count": row.task_count,
                "completed_count": int(row.completed_count or 0),
            })

    return workload


# ── 4. AI 인사이트 ──

async def get_ai_insights(db: AsyncSession, user) -> list[dict]:
    """규칙 기반 인사이트 생성 (Gemini 비사용 — 즉시 응답)"""
    team_ids = await get_user_team_ids(db, user.id)
    insights = []

    # 4-1. 이번 주 마감인데 미완료인 업무
    now = utc_now()
    week_end = (now + timedelta(days=(6 - now.weekday()))).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")

    overdue_result = await db.execute(
        select(func.count(Task.id)).where(
            access_filter(Task, user.id, team_ids),
            Task.due_date <= week_end,
            Task.due_date >= today,
            Task.status.notin_(["completed", "confirmed"]),
        )
    )
    week_due = overdue_result.scalar() or 0
    if week_due > 0:
        insights.append({
            "type": "warning",
            "message": f"이번 주 마감 업무 {week_due}건이 미완료입니다",
            "related_type": "task",
        })

    # 4-2. 마감 초과된 업무
    past_due_result = await db.execute(
        select(func.count(Task.id)).where(
            access_filter(Task, user.id, team_ids),
            Task.due_date < today,
            Task.status.notin_(["completed", "confirmed"]),
        )
    )
    past_due = past_due_result.scalar() or 0
    if past_due > 0:
        insights.append({
            "type": "warning",
            "message": f"마감일이 지난 미완료 업무가 {past_due}건입니다",
            "related_type": "task",
        })

    # 4-3. 30일 초과 미수금
    threshold_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    overdue_pay_result = await db.execute(
        select(func.count(PaymentSchedule.id)).where(
            PaymentSchedule.status.in_(["pending", "invoiced", "overdue"]),
            PaymentSchedule.due_date < threshold_date,
        )
    )
    overdue_payments = overdue_pay_result.scalar() or 0
    if overdue_payments > 0:
        insights.append({
            "type": "warning",
            "message": f"30일 초과 미수금이 {overdue_payments}건 있습니다",
            "related_type": "payment",
        })

    # 4-4. 피드백 대기 업무
    fb_pending_result = await db.execute(
        select(func.count(Task.id)).where(
            access_filter(Task, user.id, team_ids),
            Task.status == "feedback_pending",
        )
    )
    fb_pending = fb_pending_result.scalar() or 0
    if fb_pending > 0:
        insights.append({
            "type": "info",
            "message": f"발주처 피드백 대기 중인 업무가 {fb_pending}건입니다",
            "related_type": "task",
        })

    # 4-5. 활성 프로젝트 중 진행률 100% (완료 전환 제안)
    projects_result = await db.execute(
        select(Project).where(
            access_filter(Project, user.id, team_ids),
            Project.status == "active",
        )
    )
    for project in projects_result.scalars().all():
        tasks_result = await db.execute(
            select(func.count(Task.id), func.sum(case(
                (Task.status.in_(["completed", "confirmed"]), 1),
                else_=0,
            ))).where(Task.project_id == project.id)
        )
        row = tasks_result.one()
        total, completed = row[0] or 0, int(row[1] or 0)
        if total > 0 and total == completed:
            insights.append({
                "type": "suggestion",
                "message": f"'{project.project_name}' 프로젝트의 모든 업무가 완료되었습니다. 상태를 '완료'로 변경해 보세요.",
                "related_id": project.id,
                "related_type": "project",
            })

    if not insights:
        insights.append({
            "type": "info",
            "message": "현재 특별한 알림 사항이 없습니다",
        })

    return insights


# ── 5. 오늘의 브리핑 (6차 개발 Phase 2-1) ──

async def get_briefing(db: AsyncSession, user) -> dict:
    """로그인 시 대시보드 최상단에 표시할 AI 브리핑 데이터"""
    now_kst = datetime.now(KST)
    today = now_kst.strftime("%Y-%m-%d")
    tomorrow = (now_kst + timedelta(days=1)).strftime("%Y-%m-%d")
    three_days_ago = (now_kst - timedelta(days=3)).isoformat()

    # 인사말
    hour = now_kst.hour
    if 6 <= hour < 12:
        greeting = "좋은 아침"
    elif 12 <= hour < 18:
        greeting = "좋은 오후"
    else:
        greeting = "좋은 저녁"

    items = []

    # 1. 오늘 마감 업무
    today_due = await db.execute(
        select(func.count(Task.id)).where(
            Task.assignee_id == user.id,
            Task.due_date == today,
            Task.status.notin_(["completed", "confirmed"]),
        )
    )
    count = today_due.scalar() or 0
    if count > 0:
        items.append({
            "priority": 1,
            "icon": "🔴",
            "message": f"오늘 마감 업무 {count}건",
            "action": "확인하기",
            "link": "#/my-tasks",
        })

    # 2. 내일 마감 업무
    tomorrow_due = await db.execute(
        select(func.count(Task.id)).where(
            Task.assignee_id == user.id,
            Task.due_date == tomorrow,
            Task.status.notin_(["completed", "confirmed"]),
        )
    )
    count = tomorrow_due.scalar() or 0
    if count > 0:
        items.append({
            "priority": 2,
            "icon": "🟡",
            "message": f"내일 마감 업무 {count}건",
            "action": "확인하기",
            "link": "#/my-tasks",
        })

    # 3. 미확인 피드백 (최근 30일)
    thirty_days_ago = (utc_now() - timedelta(days=30))
    unread_fb = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.is_read == False,  # noqa: E712
            Notification.type.in_(["feedback_received", "revision_requested"]),
            Notification.created_at >= thirty_days_ago,
        )
    )
    count = unread_fb.scalar() or 0
    if count > 0:
        items.append({
            "priority": 3,
            "icon": "🟡",
            "message": f"고객 피드백 {count}건 미확인",
            "action": "확인하기",
            "link": "#/feedback-requests",
        })

    # 4. 읽지 않은 채팅 (단일 쿼리)
    from app.database import ChatRoomMember, RoomMessage
    from sqlalchemy.orm import aliased
    crm = aliased(ChatRoomMember)
    unread_chat_result = await db.execute(
        select(func.count(RoomMessage.id)).select_from(RoomMessage)
        .join(crm, crm.room_id == RoomMessage.room_id)
        .where(
            crm.user_id == user.id,
            RoomMessage.sender_id != user.id,
            (RoomMessage.created_at > crm.last_read_at) | (crm.last_read_at == None),  # noqa: E711
        )
    )
    unread_chat_total = unread_chat_result.scalar() or 0

    if unread_chat_total > 0:
        items.append({
            "priority": 4,
            "icon": "💬",
            "message": f"채팅 {unread_chat_total}건 읽지 않음",
            "action": "읽기",
            "link": "#/chat",
        })

    # 5. 3일간 미업데이트 업무
    stale_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.assignee_id == user.id,
            Task.status == "in_progress",
            Task.updated_at < three_days_ago,
        )
    )
    count = stale_result.scalar() or 0
    if count > 0:
        items.append({
            "priority": 5,
            "icon": "⚠️",
            "message": f"진행 중 업무 {count}건 3일간 변동 없음",
            "action": "확인하기",
            "link": "#/my-tasks",
        })

    # 6. 출근 미기록 (업무 시간일 때만: 평일 06~18시)
    weekday = now_kst.weekday()  # 0=월 ~ 6=일
    if weekday < 5 and 6 <= hour < 18:
        team_result = await db.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == user.id).limit(1)
        )
        team_row = team_result.first()
        if team_row:
            attendance_result = await db.execute(
                select(Attendance).where(
                    Attendance.user_id == user.id,
                    Attendance.team_id == team_row[0],
                    Attendance.date == today,
                )
            )
            record = attendance_result.scalar_one_or_none()
            if not record or not record.check_in:
                items.append({
                    "priority": 6,
                    "icon": "⏰",
                    "message": "오늘 출근 기록이 없어요",
                    "action": "업무 시작하기",
                    "link": "check-in",  # 프론트에서 POST /attendance/check-in 호출
                })

    return {
        "greeting": greeting,
        "user_name": user.name or user.email,
        "items": sorted(items, key=lambda x: x["priority"]),
        "empty_message": "오늘은 특별한 알림이 없어요! 좋은 하루 되세요" if not items else None,
    }
