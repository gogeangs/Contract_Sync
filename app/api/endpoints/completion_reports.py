"""완료 보고 엔드포인트 — Phase 2 (6개)"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.schemas.report import (
    CompletionReportCreate, CompletionReportUpdate, CompletionReportResponse,
)
from app.services import report_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ══════════════════════════════════════════
#  완료 보고 작성 / 조회
# ══════════════════════════════════════════

@router.post("/tasks/{task_id}/completion-report", response_model=CompletionReportResponse)
@limiter.limit("10/minute")
async def create_completion_report(
    task_id: int,
    data: CompletionReportCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """완료 보고 작성 + 발송/예약"""
    user = await require_current_user(request, db)
    try:
        report = await report_service.create_report(db, user, task_id, data)
        return await report_service.enrich_report(db, report)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"완료 보고 작성 실패: {e}")
        raise HTTPException(status_code=500, detail="완료 보고 작성에 실패했습니다")


@router.get("/tasks/{task_id}/completion-report", response_model=CompletionReportResponse)
async def get_completion_report(
    task_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """완료 보고 조회"""
    user = await require_current_user(request, db)
    try:
        report = await report_service.get_report(db, user, task_id)
        return await report_service.enrich_report(db, report)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"완료 보고 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="완료 보고 조회에 실패했습니다")


# ══════════════════════════════════════════
#  완료 보고 수정 / 삭제 / 재발송
# ══════════════════════════════════════════

@router.put("/completion-reports/{report_id}", response_model=CompletionReportResponse)
@limiter.limit("10/minute")
async def update_completion_report(
    report_id: int,
    data: CompletionReportUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """완료 보고 수정 (예약 상태만)"""
    user = await require_current_user(request, db)
    try:
        report = await report_service.update_report(db, user, report_id, data)
        return await report_service.enrich_report(db, report)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"완료 보고 수정 실패: {e}")
        raise HTTPException(status_code=500, detail="완료 보고 수정에 실패했습니다")


@router.delete("/completion-reports/{report_id}")
async def delete_completion_report(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """완료 보고 삭제 (예약 상태만)"""
    user = await require_current_user(request, db)
    try:
        await report_service.delete_report(db, user, report_id)
        return {"message": "완료 보고가 삭제되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"완료 보고 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail="완료 보고 삭제에 실패했습니다")


@router.post("/completion-reports/{report_id}/resend", response_model=CompletionReportResponse)
@limiter.limit("5/minute")
async def resend_completion_report(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """완료 보고 재발송"""
    user = await require_current_user(request, db)
    try:
        report = await report_service.resend_report(db, user, report_id)
        return await report_service.enrich_report(db, report)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"완료 보고 재발송 실패: {e}")
        raise HTTPException(status_code=500, detail="완료 보고 재발송에 실패했습니다")


# ══════════════════════════════════════════
#  AI 초안 생성
# ══════════════════════════════════════════

@router.post("/tasks/{task_id}/ai-draft-report")
@limiter.limit("5/minute")
async def ai_draft_report(
    task_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """AI 완료 보고 초안 생성"""
    user = await require_current_user(request, db)
    try:
        return await report_service.ai_draft_report(db, user, task_id)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"AI 초안 생성 실패: {e}")
        raise HTTPException(status_code=500, detail="AI 초안 생성에 실패했습니다")
