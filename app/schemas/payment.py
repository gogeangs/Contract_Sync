from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime


def _validate_date_format(v: str | None) -> str | None:
    """YYYY-MM-DD 형식 검증"""
    if v is None:
        return v
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise ValueError("날짜 형식은 YYYY-MM-DD여야 합니다 (예: 2026-03-15)")
    return v


class PaymentCreate(BaseModel):
    """결제 일정 등록"""
    payment_type: Literal["advance", "interim", "final", "milestone"] = Field(
        ..., description="결제 유형"
    )
    description: str = Field(..., min_length=1, max_length=300, description="결제 설명")
    amount: int = Field(..., gt=0, description="금액 (원)")
    due_date: Optional[str] = Field(None, description="지급 예정일 (YYYY-MM-DD)")
    document_id: Optional[int] = Field(None, description="근거 문서 ID")
    memo: Optional[str] = Field(None, description="메모")

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v):
        return _validate_date_format(v)


class PaymentUpdate(BaseModel):
    """결제 상태/금액 수정"""
    status: Optional[Literal["pending", "invoiced", "paid", "overdue"]] = None
    paid_date: Optional[str] = Field(None, description="실제 입금일")
    paid_amount: Optional[int] = Field(None, description="실제 입금액")
    memo: Optional[str] = None

    @field_validator("paid_date")
    @classmethod
    def validate_paid_date(cls, v):
        return _validate_date_format(v)


class PaymentResponse(BaseModel):
    """결제 일정 응답"""
    id: int
    project_id: int
    document_id: Optional[int] = None
    payment_type: str
    description: str
    amount: int
    due_date: Optional[str] = None
    status: str
    paid_date: Optional[str] = None
    paid_amount: Optional[int] = None
    memo: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    project_name: Optional[str] = None

    model_config = {"from_attributes": True}


class PaymentListResponse(BaseModel):
    """결제 일정 목록 응답"""
    payments: list[PaymentResponse]
    total: int


class PaymentSummary(BaseModel):
    """수금 요약 (대시보드)"""
    total_amount: int = 0
    paid_amount: int = 0
    pending_amount: int = 0
    overdue_amount: int = 0
    upcoming_payments: list[PaymentResponse] = []
