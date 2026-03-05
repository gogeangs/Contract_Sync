"""클라이언트 포털 엔드포인트 — Phase 6 (§16, 4개)"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.schemas.portal import (
    PortalTokenCreate, PortalTokenResponse, PortalDataResponse,
)
from app.services import portal_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ══════════════════════════════════════════
#  비로그인 포털 (토큰 기반)
# ══════════════════════════════════════════

@router.get("/portal/{token}/data", response_model=PortalDataResponse)
@limiter.limit("30/minute")
async def get_portal_data(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """포털 데이터 조회 (비로그인, 토큰 기반)"""
    token_obj = await portal_service.validate_portal_token(db, token)
    return await portal_service.get_portal_data(db, token_obj)


# ══════════════════════════════════════════
#  로그인 — 토큰 관리
# ══════════════════════════════════════════

@router.post("/projects/{project_id}/portal-token", response_model=PortalTokenResponse)
@limiter.limit("5/minute")
async def create_portal_token(
    project_id: int,
    data: PortalTokenCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """포털 토큰 발급"""
    user = await require_current_user(request, db)
    result = await portal_service.create_portal_token(
        db, user, project_id, data, str(request.base_url),
    )
    return PortalTokenResponse(**result)


@router.delete("/portal-tokens/{token_id}")
async def revoke_portal_token(
    token_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """포털 토큰 비활성화"""
    user = await require_current_user(request, db)
    await portal_service.revoke_portal_token(db, user, token_id)
    return {"message": "포털 토큰이 비활성화되었습니다"}


@router.get("/projects/{project_id}/portal-token")
async def get_project_portal_token(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 활성 포털 토큰 조회"""
    user = await require_current_user(request, db)
    result = await portal_service.get_portal_token_for_project(
        db, user, project_id, str(request.base_url),
    )
    if result is None:
        return {"token": None}
    return PortalTokenResponse(**result)
