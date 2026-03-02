"""AI 보고서 엔드포인트 — Phase 3 (7개)"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.schemas.report import (
    AIReportGenerate, AIReportUpdate, AIReportSend,
    AIReportResponse, AIReportListResponse,
)
from app.services import ai_report_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ══════════════════════════════════════════
#  AI 보고서 생성 / 프로젝트별 목록
# ══════════════════════════════════════════

@router.post("/projects/{project_id}/reports/generate", response_model=AIReportResponse)
@limiter.limit("3/minute")
async def generate_report(
    project_id: int,
    data: AIReportGenerate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """AI 보고서 수동 생성"""
    user = await require_current_user(request, db)
    try:
        report = await ai_report_service.generate_report(db, user, project_id, data)
        return await ai_report_service.enrich_report(db, report)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"AI 보고서 생성 실패: {e}")
        raise HTTPException(status_code=500, detail="AI 보고서 생성에 실패했습니다")


@router.get("/projects/{project_id}/reports", response_model=AIReportListResponse)
async def list_project_reports(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 보고서 목록"""
    user = await require_current_user(request, db)
    try:
        reports, total = await ai_report_service.list_project_reports(db, user, project_id)
        enriched = [await ai_report_service.enrich_report(db, r) for r in reports]
        return {"reports": enriched, "total": total}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"프로젝트 보고서 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="보고서 목록 조회에 실패했습니다")


# ══════════════════════════════════════════
#  전체 보고서 목록 (보고서 허브)
# ══════════════════════════════════════════

@router.get("/reports", response_model=AIReportListResponse)
async def list_all_reports(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """전체 보고서 목록"""
    user = await require_current_user(request, db)
    try:
        reports, total = await ai_report_service.list_all_reports(db, user, page, size)
        enriched = [await ai_report_service.enrich_report(db, r) for r in reports]
        return {"reports": enriched, "total": total}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"전체 보고서 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="보고서 목록 조회에 실패했습니다")


# ══════════════════════════════════════════
#  보고서 상세 / 편집 / 발송 / 삭제
# ══════════════════════════════════════════

@router.get("/reports/{report_id}", response_model=AIReportResponse)
async def get_report(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """보고서 상세 조회"""
    user = await require_current_user(request, db)
    try:
        report = await ai_report_service.get_report(db, user, report_id)
        return await ai_report_service.enrich_report(db, report)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"보고서 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="보고서 조회에 실패했습니다")


@router.put("/reports/{report_id}", response_model=AIReportResponse)
@limiter.limit("10/minute")
async def update_report(
    report_id: int,
    data: AIReportUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """보고서 편집 (제목/본문)"""
    user = await require_current_user(request, db)
    try:
        report = await ai_report_service.update_report(db, user, report_id, data)
        return await ai_report_service.enrich_report(db, report)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"보고서 편집 실패: {e}")
        raise HTTPException(status_code=500, detail="보고서 편집에 실패했습니다")


@router.post("/reports/{report_id}/send", response_model=AIReportResponse)
@limiter.limit("5/minute")
async def send_report(
    report_id: int,
    data: AIReportSend,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """보고서 이메일 발송"""
    user = await require_current_user(request, db)
    try:
        report = await ai_report_service.send_report(db, user, report_id, data)
        return await ai_report_service.enrich_report(db, report)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"보고서 발송 실패: {e}")
        raise HTTPException(status_code=500, detail="보고서 발송에 실패했습니다")


@router.delete("/reports/{report_id}")
async def delete_report(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """보고서 삭제"""
    user = await require_current_user(request, db)
    try:
        await ai_report_service.delete_report(db, user, report_id)
        return {"message": "보고서가 삭제되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"보고서 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail="보고서 삭제에 실패했습니다")
