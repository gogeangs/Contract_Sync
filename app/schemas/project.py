from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class ProjectCreate(BaseModel):
    """프로젝트 생성"""
    project_name: str = Field(..., min_length=1, max_length=500, description="프로젝트명")
    project_type: Literal["outsourcing", "internal", "maintenance"] = Field(
        default="outsourcing", description="프로젝트 유형"
    )
    client_id: Optional[int] = Field(None, description="발주처 ID (외주 필수, 내부 불필요)")
    description: Optional[str] = Field(None, description="설명")
    start_date: Optional[str] = Field(None, description="시작일 (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="종료일 (YYYY-MM-DD)")
    total_duration_days: Optional[int] = Field(None, description="총 기간(일)")
    contract_amount: Optional[str] = Field(None, max_length=200, description="계약 금액")
    payment_method: Optional[str] = Field(None, max_length=500, description="지급 방식")
    schedules: Optional[list[dict]] = Field(None, description="추진 일정")
    milestones: Optional[list[str]] = Field(None, description="마일스톤")


class ProjectUpdate(BaseModel):
    """프로젝트 수정"""
    project_name: Optional[str] = Field(None, min_length=1, max_length=500)
    project_type: Optional[Literal["outsourcing", "internal", "maintenance"]] = None
    client_id: Optional[int] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    total_duration_days: Optional[int] = None
    contract_amount: Optional[str] = Field(None, max_length=200)
    payment_method: Optional[str] = Field(None, max_length=500)
    schedules: Optional[list[dict]] = None
    milestones: Optional[list[str]] = None
    report_opt_in: Optional[bool] = None
    report_frequency: Optional[Literal["daily", "weekly", "monthly"]] = None


class ProjectStatusUpdate(BaseModel):
    """프로젝트 상태 변경"""
    status: str = Field(
        ...,
        pattern=r"^(planning|active|on_hold|completed|cancelled)$",
        description="프로젝트 상태",
    )


class ProjectResponse(BaseModel):
    """프로젝트 응답"""
    id: int
    user_id: int
    team_id: Optional[int] = None
    client_id: Optional[int] = None
    project_name: str
    project_type: str
    status: str
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    total_duration_days: Optional[int] = None
    contract_amount: Optional[str] = None
    payment_method: Optional[str] = None
    schedules: Optional[list[dict]] = None
    milestones: Optional[list[str]] = None
    report_opt_in: bool = False
    report_frequency: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # 집계 필드
    client_name: Optional[str] = None
    task_count: int = 0
    completed_task_count: int = 0
    document_count: int = 0

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    """프로젝트 목록 응답"""
    projects: list[ProjectResponse]
    total: int
