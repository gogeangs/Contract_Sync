"""캘린더 연동 엔드포인트 — Phase 6 (§17) + 5차 확장

connect/disconnect/sync(양방향)/status/direction 변경
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.schemas.portal import (
    CalendarConnectRequest,
    CalendarSyncDirectionRequest,
    CalendarStatusResponse,
)
from app.services import calendar_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/connect", response_model=CalendarStatusResponse)
@limiter.limit("3/minute")
async def connect_calendar(
    data: CalendarConnectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """캘린더 연동 (OAuth code 교환 + 동기화 방향 설정)"""
    user = await require_current_user(request, db)
    sync = await calendar_service.connect_calendar(
        db, user, data, sync_direction=data.sync_direction,
    )
    return sync


@router.delete("/{sync_id}")
async def disconnect_calendar(
    sync_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """캘린더 연동 해제"""
    user = await require_current_user(request, db)
    await calendar_service.disconnect_calendar(db, user, sync_id)
    return {"message": "캘린더 연동이 해제되었습니다"}


@router.post("/{sync_id}/sync")
@limiter.limit("5/minute")
async def sync_calendar(
    sync_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """캘린더 동기화 (sync_direction에 따라 CS→Google / Google→CS / 양방향 자동 판별)"""
    user = await require_current_user(request, db)
    result = await calendar_service.sync_calendar(db, user, sync_id)
    return result


@router.patch("/{sync_id}/direction", response_model=CalendarStatusResponse)
async def update_sync_direction(
    sync_id: int,
    data: CalendarSyncDirectionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """동기화 방향 변경"""
    user = await require_current_user(request, db)
    sync = await calendar_service.update_sync_direction(
        db, user, sync_id, data.sync_direction,
    )
    return sync


@router.get("/status", response_model=list[CalendarStatusResponse])
async def get_calendar_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """캘린더 연동 상태 조회"""
    user = await require_current_user(request, db)
    syncs = await calendar_service.get_calendar_status(db, user)
    return syncs
