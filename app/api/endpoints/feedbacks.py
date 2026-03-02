"""피드백 엔드포인트 — Phase 2 (3개: 비로그인 2 + 로그인 1)"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    get_db, CompletionReport, ClientFeedback, Task, User,
    TeamMember, Notification, utc_now,
)
from app.limiter import limiter
from app.api.endpoints.auth import require_current_user
from app.schemas.report import FeedbackSubmit, FeedbackResponse
from app.services.common import get_user_team_ids, get_accessible

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 헬퍼 ──

async def _validate_feedback_token(
    db: AsyncSession, token: str,
) -> CompletionReport:
    """토큰 유효성 검증 + 완료 보고 반환"""
    result = await db.execute(
        select(CompletionReport).where(CompletionReport.feedback_token == token)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="유효하지 않은 피드백 링크입니다")
    if report.feedback_token_expires_at and report.feedback_token_expires_at < utc_now():
        raise HTTPException(status_code=410, detail="피드백 링크가 만료되었습니다")
    return report


# ══════════════════════════════════════════
#  비로그인 피드백 (토큰 기반)
# ══════════════════════════════════════════

@router.get("/feedback/{token}")
async def get_feedback_info(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """피드백 정보 조회 (비로그인, 토큰 기반)"""
    report = await _validate_feedback_token(db, token)

    task = await db.get(Task, report.task_id)
    sender = await db.get(User, report.sender_id)

    # 기존 피드백 목록
    existing = (await db.execute(
        select(ClientFeedback)
        .where(ClientFeedback.completion_report_id == report.id)
        .order_by(desc(ClientFeedback.created_at))
    )).scalars().all()

    return {
        "report_id": report.id,
        "task_name": task.task_name if task else None,
        "subject": report.subject,
        "body_html": report.body_html,
        "sender_name": (sender.name or sender.email) if sender else None,
        "sent_at": report.sent_at,
        "existing_feedbacks": [
            {
                "id": f.id,
                "feedback_type": f.feedback_type,
                "content": f.content,
                "client_name": f.client_name,
                "created_at": f.created_at,
            }
            for f in existing
        ],
    }


@router.post("/feedback/{token}", response_model=FeedbackResponse)
@limiter.limit("10/minute")
async def submit_feedback(
    token: str,
    data: FeedbackSubmit,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """피드백 제출 (비로그인, IP rate limit)"""
    report = await _validate_feedback_token(db, token)

    # IP 추출
    ip_address = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not ip_address:
        ip_address = request.client.host if request.client else None

    # revision은 내용 필수
    if data.feedback_type == "revision" and not data.content:
        raise HTTPException(status_code=400, detail="수정 요청 시 내용을 입력해주세요")

    # 피드백 생성
    feedback = ClientFeedback(
        completion_report_id=report.id,
        task_id=report.task_id,
        feedback_type=data.feedback_type,
        content=data.content,
        client_name=data.client_name,
        ip_address=ip_address,
    )
    db.add(feedback)

    # 업무 상태 변경
    task = await db.get(Task, report.task_id)
    if task:
        if data.feedback_type == "confirmed":
            task.status = "confirmed"
        elif data.feedback_type == "revision":
            task.status = "revision_requested"

    # 알림 대상 수집
    notify_targets = set()
    if task:
        if task.assignee_id:
            notify_targets.add(task.assignee_id)
        notify_targets.add(report.sender_id)

        # revision → 팀 전체 알림
        if data.feedback_type == "revision" and task.team_id:
            members = (await db.execute(
                select(TeamMember.user_id).where(TeamMember.team_id == task.team_id)
            )).scalars().all()
            notify_targets.update(members)

    # 알림 생성
    type_labels = {"confirmed": "확인 완료", "revision": "수정 요청", "comment": "코멘트"}
    type_label = type_labels.get(data.feedback_type, data.feedback_type)
    client_display = data.client_name or "발주처"

    for uid in notify_targets:
        db.add(Notification(
            user_id=uid,
            type="feedback_received",
            title=f"{client_display}님이 '{task.task_name}'에 {type_label} 피드백을 남겼습니다",
            message=data.content[:100] if data.content else None,
            link=json.dumps({"project_id": task.project_id, "task_id": task.id}) if task else None,
        ))

    await db.commit()
    await db.refresh(feedback)
    return feedback


# ══════════════════════════════════════════
#  로그인 피드백 이력 조회
# ══════════════════════════════════════════

@router.get("/tasks/{task_id}/feedbacks")
async def list_task_feedbacks(
    task_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """업무의 피드백 이력 (로그인 필수)"""
    user = await require_current_user(request, db)
    team_ids = await get_user_team_ids(db, user.id)

    task = await get_accessible(db, Task, task_id, user.id, team_ids)
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    feedbacks = (await db.execute(
        select(ClientFeedback)
        .where(ClientFeedback.task_id == task_id)
        .order_by(desc(ClientFeedback.created_at))
    )).scalars().all()

    return {
        "feedbacks": [
            {
                "id": f.id,
                "completion_report_id": f.completion_report_id,
                "task_id": f.task_id,
                "feedback_type": f.feedback_type,
                "content": f.content,
                "client_name": f.client_name,
                "created_at": f.created_at,
            }
            for f in feedbacks
        ],
        "total": len(feedbacks),
    }
