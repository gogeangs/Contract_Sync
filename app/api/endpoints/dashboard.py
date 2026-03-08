"""대시보드 엔드포인트 — Phase 7 (§18, 4개) + 2차 개발 주간 리포트"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.schemas.dashboard import DashboardSummary, RevenueData, WorkloadItem, AIInsight
from app.services import dashboard_service
from app.services.weekly_report import get_weekly_report_data

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


@router.get("/weekly-report")
async def get_weekly_report(
    request: Request,
    team_id: Optional[int] = Query(None, description="팀 ID (없으면 개인 리포트)"),
    week_offset: int = Query(0, ge=-52, le=0, description="주 오프셋 (0=이번 주, -1=지난 주)"),
    db: AsyncSession = Depends(get_db),
):
    """주간 요약 리포트 (#10)"""
    user = await require_current_user(request, db)
    report = await get_weekly_report_data(db, team_id, user.id, week_offset)
    if not report:
        return {"summary": "데이터 없음", "stats": {}, "completed": [], "in_progress": [], "overdue": [], "new_tasks": []}
    return report
