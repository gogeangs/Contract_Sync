from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import re


class ClientCreate(BaseModel):
    """발주처 등록"""
    name: str = Field(..., min_length=1, max_length=200, description="발주처명")
    contact_name: Optional[str] = Field(None, max_length=100, description="담당자명")
    contact_email: Optional[str] = Field(None, max_length=200, description="담당자 이메일")
    contact_phone: Optional[str] = Field(None, max_length=20, description="담당자 전화번호")
    address: Optional[str] = Field(None, description="주소")
    category: Optional[str] = Field(None, max_length=50, description="업종/분류")
    memo: Optional[str] = Field(None, max_length=2000, description="메모")

    @field_validator("contact_email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("올바른 이메일 형식이 아닙니다")
        return v


class ClientUpdate(BaseModel):
    """발주처 수정"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_email: Optional[str] = Field(None, max_length=200)
    contact_phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)
    memo: Optional[str] = Field(None, max_length=2000)

    @field_validator("contact_email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("올바른 이메일 형식이 아닙니다")
        return v


class ClientResponse(BaseModel):
    """발주처 응답"""
    id: int
    user_id: int
    team_id: Optional[int] = None
    name: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    category: Optional[str] = None
    memo: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    active_project_count: int = 0
    total_revenue: int = 0

    model_config = {"from_attributes": True}


class ClientListResponse(BaseModel):
    """발주처 목록 응답"""
    clients: list[ClientResponse]
    total: int
