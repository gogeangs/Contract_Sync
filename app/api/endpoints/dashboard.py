"""대시보드 엔드포인트 — Phase 7 (§18, 4개)"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.schemas.dashboard import DashboardSummary, RevenueData, WorkloadItem, AIInsight
from app.services import dashboard_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """대시보드 통계 (6개 카드)"""
    user = await require_current_user(request, db)
    return await dashboard_service.get_summary(db, user)


@router.get("/revenue", response_model=RevenueData)
async def get_revenue(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """매출 추이 (최근 6개월)"""
    user = await require_current_user(request, db)
    return await dashboard_service.get_revenue(db, user)


@router.get("/workload", response_model=list[WorkloadItem])
async def get_workload(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """팀 워크로드"""
    user = await require_current_user(request, db)
    return await dashboard_service.get_workload(db, user)


@router.get("/ai-insights", response_model=list[AIInsight])
@limiter.limit("3/minute")
async def get_ai_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """AI 인사이트 (규칙 기반)"""
    user = await require_current_user(request, db)
    return await dashboard_service.get_ai_insights(db, user)
