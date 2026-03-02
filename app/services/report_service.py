"""완료 보고 서비스 — Phase 2"""
import asyncio
import json
import logging
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    CompletionReport, Task, Project, Client, User,
    Notification, async_session, utc_now,
)
from app.services.common import (
    get_user_team_ids, check_team_permission, log_activity, get_accessible,
)

logger = logging.getLogger(__name__)

FEEDBACK_TOKEN_EXPIRY_DAYS = 30
_BASE_URL = "http://127.0.0.1:8000"  # TODO: 설정에서 읽기


# ── 이메일 백그라운드 발송 ──

async def _send_report_email_background(report_id: int):
    """완료 보고 이메일을 백그라운드로 발송 (실패 시 status→failed)"""
    from app.services.email_service import send_completion_report_email

    try:
        async with async_session() as db:
            report = await db.get(CompletionReport, report_id)
            if not report or report.status not in ("sent",):
                return

            task = await db.get(Task, report.task_id)
            project = await db.get(Project, report.project_id) if report.project_id else None
            sender = await db.get(User, report.sender_id)

            feedback_url = f"{_BASE_URL}/#/feedback/{report.feedback_token}"

            success = await send_completion_report_email(
                recipient_email=report.recipient_email,
                cc_emails=report.cc_emails,
                subject=report.subject,
                project_name=project.project_name if project else "",
                task_name=task.task_name if task else "",
                sender_name=(sender.name or sender.email) if sender else "",
                body_content=report.body_html,
                feedback_url=feedback_url,
            )

            if not success:
                report.status = "failed"
                await db.commit()
                logger.error(f"완료 보고 이메일 발송 실패 → status=failed: report_id={report_id}")
    except Exception as e:
        logger.error(f"완료 보고 이메일 백그라운드 발송 오류: {e}")


# ── 공통 헬퍼 ──

async def _get_task_with_access(
    db: AsyncSession, user: User, task_id: int,
) -> Task:
    """업무 접근 권한 확인 후 반환"""
    team_ids = await get_user_team_ids(db, user.id)
    task = await get_accessible(db, Task, task_id, user.id, team_ids)
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")
    return task


async def _get_report_with_access(
    db: AsyncSession, user: User, report_id: int,
) -> tuple[CompletionReport, Task]:
    """보고 + 업무 접근 권한 확인 후 반환"""
    report = await db.get(CompletionReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="완료 보고를 찾을 수 없습니다")
    task = await _get_task_with_access(db, user, report.task_id)
    return report, task


async def enrich_report(db: AsyncSession, report: CompletionReport) -> dict:
    """응답용 dict 변환 (sender_name, task_name 조인)"""
    sender = await db.get(User, report.sender_id)
    task = await db.get(Task, report.task_id)
    return {
        "id": report.id,
        "task_id": report.task_id,
        "project_id": report.project_id,
        "sender_id": report.sender_id,
        "recipient_email": report.recipient_email,
        "cc_emails": report.cc_emails,
        "subject": report.subject,
        "body_html": report.body_html,
        "attachments": report.attachments,
        "feedback_token": report.feedback_token,
        "status": report.status,
        "scheduled_at": report.scheduled_at,
        "sent_at": report.sent_at,
        "created_at": report.created_at,
        "sender_name": (sender.name or sender.email) if sender else None,
        "task_name": task.task_name if task else None,
    }


# ── 완료 보고 CRUD ──

async def create_report(
    db: AsyncSession, user: User, task_id: int, data,
) -> CompletionReport:
    """완료 보고 생성 + feedback_token 발급"""
    task = await _get_task_with_access(db, user, task_id)

    # 검증
    if not task.is_client_facing:
        raise HTTPException(status_code=400, detail="발주처 대면 업무만 완료 보고를 작성할 수 있습니다")
    if task.status not in ("completed", "report_sent"):
        raise HTTPException(status_code=400, detail="완료된 업무만 보고를 작성할 수 있습니다")
    if not task.project_id:
        raise HTTPException(status_code=400, detail="프로젝트에 소속된 업무만 완료 보고를 작성할 수 있습니다")

    await check_team_permission(db, task.team_id, user.id, "report.create")

    # 중복 방지
    existing = (await db.execute(
        select(CompletionReport).where(
            CompletionReport.task_id == task_id,
            CompletionReport.status != "failed",
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="이미 완료 보고가 존재합니다")

    # 토큰 생성
    token = secrets.token_urlsafe(48)
    expires_at = utc_now() + timedelta(days=FEEDBACK_TOKEN_EXPIRY_DAYS)

    # 즉시 발송 vs 예약
    if data.scheduled_at:
        status = "scheduled"
        sent_at = None
    else:
        status = "sent"
        sent_at = utc_now()

    report = CompletionReport(
        task_id=task_id,
        project_id=task.project_id,
        sender_id=user.id,
        recipient_email=data.recipient_email,
        cc_emails=data.cc_emails,
        subject=data.subject,
        body_html=data.body_html,
        feedback_token=token,
        feedback_token_expires_at=expires_at,
        status=status,
        scheduled_at=data.scheduled_at,
        sent_at=sent_at,
    )
    db.add(report)
    await db.flush()

    # 업무 상태 변경
    task.status = "report_sent"

    # 활동 로그
    await log_activity(
        db, user.id, "send", "completion_report", task.task_name,
        project_id=task.project_id, team_id=task.team_id,
        detail=f"수신: {data.recipient_email}",
    )

    # 담당자 알림
    if task.assignee_id and task.assignee_id != user.id:
        db.add(Notification(
            user_id=task.assignee_id,
            type="completion_report",
            title=f"'{task.task_name}' 완료 보고가 발송되었습니다",
            message=f"수신자: {data.recipient_email}",
            link=json.dumps({"project_id": task.project_id, "task_id": task_id}),
        ))

    await db.commit()
    await db.refresh(report)

    # 즉시 발송 → 백그라운드 이메일 전송
    if status == "sent":
        asyncio.create_task(_send_report_email_background(report.id))

    return report


async def get_report(
    db: AsyncSession, user: User, task_id: int,
) -> CompletionReport:
    """업무의 최신 완료 보고 조회"""
    await _get_task_with_access(db, user, task_id)

    result = await db.execute(
        select(CompletionReport)
        .where(CompletionReport.task_id == task_id)
        .order_by(desc(CompletionReport.created_at))
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="완료 보고를 찾을 수 없습니다")
    return report


async def update_report(
    db: AsyncSession, user: User, report_id: int, data,
) -> CompletionReport:
    """완료 보고 수정 (예약 상태만)"""
    report, task = await _get_report_with_access(db, user, report_id)

    if report.status != "scheduled":
        raise HTTPException(status_code=400, detail="예약 상태의 보고만 수정할 수 있습니다")

    await check_team_permission(db, task.team_id, user.id, "report.create")

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(report, field, value)

    await log_activity(
        db, user.id, "update", "completion_report", task.task_name,
        project_id=task.project_id, team_id=task.team_id,
    )
    await db.commit()
    await db.refresh(report)
    return report


async def delete_report(
    db: AsyncSession, user: User, report_id: int,
) -> None:
    """완료 보고 삭제 (예약 상태만)"""
    report, task = await _get_report_with_access(db, user, report_id)

    if report.status != "scheduled":
        raise HTTPException(status_code=400, detail="예약 상태의 보고만 삭제할 수 있습니다")

    await check_team_permission(db, task.team_id, user.id, "report.create")

    await log_activity(
        db, user.id, "delete", "completion_report", task.task_name,
        project_id=task.project_id, team_id=task.team_id,
    )

    # 다른 active 보고 없으면 task → completed 복원
    other = (await db.execute(
        select(CompletionReport.id).where(
            CompletionReport.task_id == task.id,
            CompletionReport.id != report_id,
            CompletionReport.status != "failed",
        )
    )).scalar_one_or_none()
    if not other:
        task.status = "completed"

    await db.delete(report)
    await db.commit()


async def resend_report(
    db: AsyncSession, user: User, report_id: int,
) -> CompletionReport:
    """완료 보고 재발송"""
    report, task = await _get_report_with_access(db, user, report_id)

    if report.status not in ("sent", "failed"):
        raise HTTPException(status_code=400, detail="발송 또는 실패 상태의 보고만 재발송할 수 있습니다")

    await check_team_permission(db, task.team_id, user.id, "report.send")

    # 토큰 재발급
    report.feedback_token = secrets.token_urlsafe(48)
    report.feedback_token_expires_at = utc_now() + timedelta(days=FEEDBACK_TOKEN_EXPIRY_DAYS)
    report.status = "sent"
    report.sent_at = utc_now()

    await log_activity(
        db, user.id, "send", "completion_report", task.task_name,
        project_id=task.project_id, team_id=task.team_id,
        detail="재발송",
    )
    await db.commit()
    await db.refresh(report)

    # 백그라운드 이메일 전송
    asyncio.create_task(_send_report_email_background(report.id))

    return report


# ── AI 초안 ──

async def ai_draft_report(
    db: AsyncSession, user: User, task_id: int,
) -> dict:
    """AI 완료 보고 초안 생성"""
    task = await _get_task_with_access(db, user, task_id)

    if not task.is_client_facing:
        raise HTTPException(status_code=400, detail="발주처 대면 업무만 AI 초안을 생성할 수 있습니다")

    project = await db.get(Project, task.project_id) if task.project_id else None

    # 발주처 정보
    client = None
    if project and project.client_id:
        client = await db.get(Client, project.client_id)

    context = {
        "task_name": task.task_name,
        "project_name": project.project_name if project else "",
        "client_name": client.name if client else "발주처",
        "sender_name": user.name or user.email,
        "completed_at": task.completed_at.isoformat() if hasattr(task, "completed_at") and task.completed_at else "",
        "note": task.note if hasattr(task, "note") and task.note else "",
    }

    from app.services.gemini_service import GeminiService
    try:
        gemini = GeminiService()
        return await gemini.generate_completion_draft(context)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
