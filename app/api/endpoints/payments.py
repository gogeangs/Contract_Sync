"""수금 관리 엔드포인트 — Phase 4 (5개)"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.schemas.payment import (
    PaymentCreate, PaymentUpdate, PaymentResponse,
    PaymentListResponse, PaymentSummary,
)
from app.services import payment_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ══════════════════════════════════════════
#  결제 일정 등록 / 프로젝트별 목록
# ══════════════════════════════════════════

@router.post("/projects/{project_id}/payments", response_model=PaymentResponse)
@limiter.limit("20/minute")
async def create_payment(
    project_id: int,
    data: PaymentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """결제 일정 등록"""
    user = await require_current_user(request, db)
    try:
        payment = await payment_service.create_payment(db, user, project_id, data)
        return await payment_service.enrich_payment(db, payment)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"결제 일정 등록 실패: {e}")
        raise HTTPException(status_code=500, detail="결제 일정 등록에 실패했습니다")


@router.get("/projects/{project_id}/payments", response_model=PaymentListResponse)
async def list_project_payments(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 결제 일정 목록"""
    user = await require_current_user(request, db)
    try:
        payments, total = await payment_service.list_project_payments(db, user, project_id)
        enriched = [await payment_service.enrich_payment(db, p) for p in payments]
        return {"payments": enriched, "total": total}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"프로젝트 결제 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="결제 목록 조회에 실패했습니다")


# ══════════════════════════════════════════
#  수금 요약 / 전체 목록 / 수정
# ══════════════════════════════════════════

@router.get("/payments/summary", response_model=PaymentSummary)
async def get_payment_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """전체 수금 요약 (대시보드)"""
    user = await require_current_user(request, db)
    try:
        summary = await payment_service.get_summary(db, user)
        # upcoming_payments enrich
        enriched_upcoming = [
            await payment_service.enrich_payment(db, p)
            for p in summary["upcoming_payments"]
        ]
        return {
            "total_amount": summary["total_amount"],
            "paid_amount": summary["paid_amount"],
            "pending_amount": summary["pending_amount"],
            "overdue_amount": summary["overdue_amount"],
            "upcoming_payments": enriched_upcoming,
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"수금 요약 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="수금 요약 조회에 실패했습니다")


@router.get("/payments", response_model=PaymentListResponse)
async def list_all_payments(
    request: Request,
    status: str | None = Query(None, description="필터: pending|invoiced|paid|overdue"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """전체 수금 목록"""
    user = await require_current_user(request, db)
    try:
        payments, total = await payment_service.list_all_payments(db, user, status, page, size)
        enriched = [await payment_service.enrich_payment(db, p) for p in payments]
        return {"payments": enriched, "total": total}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"전체 수금 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="수금 목록 조회에 실패했습니다")


@router.patch("/payments/{payment_id}", response_model=PaymentResponse)
@limiter.limit("20/minute")
async def update_payment(
    payment_id: int,
    data: PaymentUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """결제 상태/금액 수정"""
    user = await require_current_user(request, db)
    try:
        payment = await payment_service.update_payment(db, user, payment_id, data)
        return await payment_service.enrich_payment(db, payment)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"결제 수정 실패: {e}")
        raise HTTPException(status_code=500, detail="결제 수정에 실패했습니다")
