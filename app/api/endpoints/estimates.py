"""AI 견적서 엔드포인트 — Phase 4 (2개)"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.schemas.estimate import (
    EstimateGenerateRequest, EstimateResponse,
    EstimateExportRequest, EstimateExportResponse,
)
from app.services import estimate_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ai/estimate/generate", response_model=EstimateResponse)
@limiter.limit("3/minute")
async def generate_estimate(
    data: EstimateGenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """AI 견적서 생성"""
    user = await require_current_user(request, db)
    try:
        result = await estimate_service.generate_estimate(db, user, data)
        return EstimateResponse(**result)
    except ValidationError as e:
        logger.warning(f"AI 견적 응답 형식 오류: {e}")
        raise HTTPException(
            status_code=422,
            detail="AI가 생성한 견적 데이터 형식이 올바르지 않습니다. 다시 시도해 주세요.",
        )
    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error(f"AI 견적 생성 실패: {e}")
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(f"AI 견적 생성 실패: {e}")
        raise HTTPException(status_code=500, detail="AI 견적 생성에 실패했습니다")


@router.post("/ai/estimate/export-sheet", response_model=EstimateExportResponse)
@limiter.limit("5/minute")
async def export_estimate_sheet(
    data: EstimateExportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """견적서 Google Sheet 내보내기"""
    user = await require_current_user(request, db)
    try:
        result = await estimate_service.export_to_sheet(db, user, data)
        return result
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"견적서 Sheet 내보내기 실패: {e}")
        raise HTTPException(status_code=500, detail="견적서 내보내기에 실패했습니다")
