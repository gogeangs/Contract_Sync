"""클라이언트 포털 서비스 — Phase 6 (§16)

비로그인 토큰 기반 프로젝트 현황 조회 + 토큰 관리.
"""
import logging
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    PortalToken, Project, Task, Client, CompletionReport, utc_now,
)
from app.services.common import (
    get_user_team_ids, get_accessible, log_activity,
)

logger = logging.getLogger(__name__)


# ── 토큰 검증 (비로그인) ──

async def validate_portal_token(db: AsyncSession, token: str) -> PortalToken:
    """포털 토큰 유효성 + 만료 검증"""
    result = await db.execute(
        select(PortalToken).where(
            PortalToken.token == token,
            PortalToken.is_active == True,  # noqa: E712
        )
    )
    token_obj = result.scalar_one_or_none()
    if not token_obj:
        raise HTTPException(status_code=404, detail="유효하지 않은 포털 링크입니다")
    if token_obj.expires_at and token_obj.expires_at < utc_now():
        raise HTTPException(status_code=410, detail="포털 링크가 만료되었습니다")
    return token_obj


# ── 토큰 발급 (로그인) ──

async def create_portal_token(
    db: AsyncSession, user, project_id: int, data, base_url: str,
) -> dict:
    """포털 토큰 발급. 기존 활성 토큰은 비활성화 후 신규 발급."""
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    if not project.client_id:
        raise HTTPException(status_code=400, detail="발주처가 지정되지 않은 프로젝트입니다")

    # 기존 활성 토큰 비활성화
    existing = await db.execute(
        select(PortalToken).where(
            PortalToken.project_id == project_id,
            PortalToken.is_active == True,  # noqa: E712
        )
    )
    for old in existing.scalars().all():
        old.is_active = False

    # 만료일 계산
    expires_at = data.expires_at
    if not expires_at and project.end_date:
        from datetime import datetime
        try:
            end_dt = datetime.strptime(project.end_date, "%Y-%m-%d")
            expires_at = end_dt + timedelta(days=30)
        except ValueError:
            pass

    # 토큰 생성
    token_str = secrets.token_urlsafe(48)
    portal_token = PortalToken(
        client_id=project.client_id,
        project_id=project_id,
        token=token_str,
        expires_at=expires_at,
    )
    db.add(portal_token)
    await db.flush()

    await log_activity(
        db, user.id, "create", "portal_token", project.project_name,
        project_id=project_id, team_id=project.team_id,
    )
    await db.commit()
    await db.refresh(portal_token)

    portal_url = f"{str(base_url).rstrip('/')}#/portal/{token_str}"
    return {
        "id": portal_token.id,
        "client_id": portal_token.client_id,
        "project_id": portal_token.project_id,
        "token": portal_token.token,
        "portal_url": portal_url,
        "expires_at": portal_token.expires_at,
        "is_active": portal_token.is_active,
        "created_at": portal_token.created_at,
    }


# ── 토큰 폐기 (로그인) ──

async def revoke_portal_token(db: AsyncSession, user, token_id: int):
    """포털 토큰 비활성화"""
    result = await db.execute(
        select(PortalToken).where(PortalToken.id == token_id)
    )
    token_obj = result.scalar_one_or_none()
    if not token_obj:
        raise HTTPException(status_code=404, detail="토큰을 찾을 수 없습니다")

    # 프로젝트 접근 권한 확인
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, token_obj.project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=403, detail="권한이 없습니다")

    token_obj.is_active = False
    await log_activity(
        db, user.id, "delete", "portal_token", project.project_name,
        project_id=project.id, team_id=project.team_id,
    )
    await db.commit()


# ── 프로젝트별 활성 토큰 조회 (로그인) ──

async def get_portal_token_for_project(
    db: AsyncSession, user, project_id: int, base_url: str,
) -> dict | None:
    """프로젝트의 활성 포털 토큰 조회"""
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    result = await db.execute(
        select(PortalToken).where(
            PortalToken.project_id == project_id,
            PortalToken.is_active == True,  # noqa: E712
        )
    )
    token_obj = result.scalar_one_or_none()
    if not token_obj:
        return None

    portal_url = f"{str(base_url).rstrip('/')}#/portal/{token_obj.token}"
    return {
        "id": token_obj.id,
        "client_id": token_obj.client_id,
        "project_id": token_obj.project_id,
        "token": token_obj.token,
        "portal_url": portal_url,
        "expires_at": token_obj.expires_at,
        "is_active": token_obj.is_active,
        "created_at": token_obj.created_at,
    }


# ── 포털 데이터 조회 (비로그인) ──

async def get_portal_data(db: AsyncSession, token_obj: PortalToken) -> dict:
    """포털 데이터 조립 — 프로젝트 정보 + 클라이언트 공개 업무 + 보고서"""
    project = await db.get(Project, token_obj.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    client = await db.get(Client, token_obj.client_id) if token_obj.client_id else None

    # is_client_facing=True 업무만 조회
    tasks_result = await db.execute(
        select(Task).where(
            Task.project_id == project.id,
            Task.is_client_facing == True,  # noqa: E712
        )
    )
    tasks = tasks_result.scalars().all()

    # 진행률 계산
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status in ("completed", "confirmed"))
    progress = round((completed / total * 100), 1) if total > 0 else 0.0

    # 완료 보고서 (피드백 대기 중인 것)
    pending_fb_result = await db.execute(
        select(CompletionReport, Task.task_name).join(
            Task, CompletionReport.task_id == Task.id
        ).where(
            CompletionReport.project_id == project.id,
            CompletionReport.feedback_token != None,  # noqa: E711
            CompletionReport.status == "sent",
        )
    )
    pending_feedbacks = [
        {
            "report_id": r.id,
            "task_name": task_name,
            "feedback_token": r.feedback_token,
        }
        for r, task_name in pending_fb_result.all()
    ]

    # 완료 보고서 목록
    reports_result = await db.execute(
        select(CompletionReport, Task.task_name).join(
            Task, CompletionReport.task_id == Task.id
        ).where(
            CompletionReport.project_id == project.id,
            CompletionReport.status == "sent",
        )
    )
    reports = [
        {
            "id": r.id,
            "task_name": task_name,
            "status": r.status,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        }
        for r, task_name in reports_result.all()
    ]

    return {
        "project_name": project.project_name,
        "project_type": project.project_type,
        "status": project.status,
        "start_date": project.start_date,
        "end_date": project.end_date,
        "progress_percent": progress,
        "client_name": client.name if client else None,
        "tasks": [
            {
                "id": t.id,
                "task_name": t.task_name,
                "status": t.status,
                "due_date": t.due_date,
                "phase": t.phase,
            }
            for t in tasks
        ],
        "pending_feedbacks": pending_feedbacks,
        "reports": reports,
    }
