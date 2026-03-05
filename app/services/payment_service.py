"""수금 관리 서비스 — Phase 4"""
import logging
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import PaymentSchedule, Project, utc_now
from app.services.common import (
    get_user_team_ids, access_filter, check_team_permission, log_activity, get_accessible,
)

logger = logging.getLogger(__name__)

# 허용되는 상태 전이
_VALID_TRANSITIONS = {
    "pending": {"invoiced", "overdue"},
    "invoiced": {"paid"},
    "overdue": {"paid"},
    "paid": set(),  # 역방향 불가
}


# ── enrich ──

async def enrich_payment(db: AsyncSession, payment: PaymentSchedule) -> dict:
    """응답용 dict 변환 (project_name 조인)"""
    project = await db.get(Project, payment.project_id)
    return {
        "id": payment.id,
        "project_id": payment.project_id,
        "document_id": payment.document_id,
        "payment_type": payment.payment_type,
        "description": payment.description,
        "amount": payment.amount,
        "due_date": payment.due_date,
        "status": payment.status,
        "paid_date": payment.paid_date,
        "paid_amount": payment.paid_amount,
        "memo": payment.memo,
        "created_at": payment.created_at,
        "updated_at": payment.updated_at,
        "project_name": project.project_name if project else None,
    }


# ── CRUD ──

async def create_payment(
    db: AsyncSession, user, project_id: int, data,
) -> PaymentSchedule:
    """결제 일정 등록"""
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    await check_team_permission(db, project.team_id, user.id, "payment.create")

    payment = PaymentSchedule(
        project_id=project_id,
        document_id=data.document_id,
        payment_type=data.payment_type,
        description=data.description,
        amount=data.amount,
        due_date=data.due_date,
        memo=data.memo,
        status="pending",
    )
    db.add(payment)
    await db.flush()

    await log_activity(
        db, user.id, "create", "payment", data.description,
        project_id=project_id, team_id=project.team_id,
        detail=f"{data.payment_type} / {data.amount:,}원",
    )
    await db.commit()
    await db.refresh(payment)
    return payment


async def list_project_payments(
    db: AsyncSession, user, project_id: int,
) -> tuple[list[PaymentSchedule], int]:
    """프로젝트별 결제 일정 목록"""
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    result = await db.execute(
        select(PaymentSchedule)
        .where(PaymentSchedule.project_id == project_id)
        .order_by(PaymentSchedule.due_date.asc())
    )
    payments = result.scalars().all()
    return payments, len(payments)


async def list_all_payments(
    db: AsyncSession, user, status: str | None = None,
    page: int = 1, size: int = 20,
) -> tuple[list[PaymentSchedule], int]:
    """전체 결제 일정 목록 (접근 가능한 프로젝트만, 필터+페이지네이션)"""
    team_ids = await get_user_team_ids(db, user.id)

    base = (
        select(PaymentSchedule)
        .join(Project, PaymentSchedule.project_id == Project.id)
        .where(access_filter(Project, user.id, team_ids))
    )
    count_base = (
        select(func.count(PaymentSchedule.id))
        .join(Project, PaymentSchedule.project_id == Project.id)
        .where(access_filter(Project, user.id, team_ids))
    )

    if status:
        base = base.where(PaymentSchedule.status == status)
        count_base = count_base.where(PaymentSchedule.status == status)

    # 총 개수
    count_q = await db.execute(count_base)
    total = count_q.scalar() or 0

    # 페이지네이션
    offset = (page - 1) * size
    result = await db.execute(
        base.order_by(PaymentSchedule.due_date.asc())
        .offset(offset).limit(size)
    )
    payments = result.scalars().all()

    return payments, total


async def get_payment(
    db: AsyncSession, user, payment_id: int,
) -> PaymentSchedule:
    """결제 일정 상세 조회 (접근 권한 확인)"""
    payment = await db.get(PaymentSchedule, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="결제 일정을 찾을 수 없습니다")

    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, payment.project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="결제 일정을 찾을 수 없습니다")

    return payment


async def update_payment(
    db: AsyncSession, user, payment_id: int, data,
) -> PaymentSchedule:
    """결제 상태/금액 수정 (PATCH)"""
    payment = await get_payment(db, user, payment_id)

    project = await db.get(Project, payment.project_id)
    await check_team_permission(db, project.team_id, user.id, "payment.update")

    updates = data.model_dump(exclude_unset=True)

    # 상태 전이 검증
    if "status" in updates:
        new_status = updates["status"]
        allowed = _VALID_TRANSITIONS.get(payment.status, set())
        if new_status != payment.status and new_status not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"'{payment.status}' → '{new_status}' 상태 전환이 허용되지 않습니다",
            )

    # paid_date 설정 시 status 자동 "paid" 전환
    if "paid_date" in updates and updates["paid_date"]:
        if payment.status in ("invoiced", "overdue", "pending"):
            updates["status"] = "paid"

    for field, value in updates.items():
        setattr(payment, field, value)

    detail_parts = []
    if "status" in updates:
        detail_parts.append(f"상태: {updates['status']}")
    if "paid_amount" in updates:
        detail_parts.append(f"입금액: {updates['paid_amount']:,}원")

    await log_activity(
        db, user.id, "update", "payment", payment.description,
        project_id=payment.project_id, team_id=project.team_id,
        detail=" / ".join(detail_parts) if detail_parts else None,
    )
    await db.commit()
    await db.refresh(payment)
    return payment


async def get_summary(db: AsyncSession, user) -> dict:
    """수금 요약 (대시보드용)"""
    team_ids = await get_user_team_ids(db, user.id)

    af = access_filter(Project, user.id, team_ids)

    # 전체 금액
    total_q = await db.execute(
        select(func.coalesce(func.sum(PaymentSchedule.amount), 0))
        .join(Project, PaymentSchedule.project_id == Project.id)
        .where(af)
    )
    total_amount = total_q.scalar() or 0

    # 입금 완료 금액
    paid_q = await db.execute(
        select(func.coalesce(func.sum(PaymentSchedule.paid_amount), 0))
        .join(Project, PaymentSchedule.project_id == Project.id)
        .where(af, PaymentSchedule.status == "paid")
    )
    paid_amount = paid_q.scalar() or 0

    # 대기 금액 (pending + invoiced)
    pending_q = await db.execute(
        select(func.coalesce(func.sum(PaymentSchedule.amount), 0))
        .join(Project, PaymentSchedule.project_id == Project.id)
        .where(af, PaymentSchedule.status.in_(["pending", "invoiced"]))
    )
    pending_amount = pending_q.scalar() or 0

    # 연체 금액
    overdue_q = await db.execute(
        select(func.coalesce(func.sum(PaymentSchedule.amount), 0))
        .join(Project, PaymentSchedule.project_id == Project.id)
        .where(af, PaymentSchedule.status == "overdue")
    )
    overdue_amount = overdue_q.scalar() or 0

    # 임박 결제 (14일 이내, pending/invoiced)
    today = utc_now().strftime("%Y-%m-%d")
    future_14 = (utc_now() + timedelta(days=14)).strftime("%Y-%m-%d")

    upcoming_q = await db.execute(
        select(PaymentSchedule)
        .join(Project, PaymentSchedule.project_id == Project.id)
        .where(
            af,
            PaymentSchedule.status.in_(["pending", "invoiced"]),
            PaymentSchedule.due_date != None,  # noqa: E711
            PaymentSchedule.due_date >= today,
            PaymentSchedule.due_date <= future_14,
        )
        .order_by(PaymentSchedule.due_date.asc())
        .limit(10)
    )
    upcoming = upcoming_q.scalars().all()

    return {
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "pending_amount": pending_amount,
        "overdue_amount": overdue_amount,
        "upcoming_payments": upcoming,
    }
