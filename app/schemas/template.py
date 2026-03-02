from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


# ── 템플릿 중첩 모델 ──

class TaskTemplateItem(BaseModel):
    """업무 템플릿 항목"""
    task_name: str = Field(..., min_length=1, max_length=300)
    phase: str = Field(..., min_length=1, max_length=50)
    relative_due_days: int = Field(..., ge=0, description="시작일 기준 상대 일수")
    priority: Literal["긴급", "높음", "보통", "낮음"] = Field(default="보통")
    is_client_facing: bool = Field(default=False, description="고객 대면 여부")


class ScheduleTemplateItem(BaseModel):
    """일정 템플릿 항목"""
    phase: str = Field(..., min_length=1, max_length=50)
    relative_start_days: int = Field(..., ge=0)
    duration_days: int = Field(..., ge=1)


# ── 프로젝트 템플릿 ──

class TemplateCreate(BaseModel):
    """프로젝트 템플릿 저장"""
    name: str = Field(..., min_length=1, max_length=200, description="템플릿명")
    project_type: Literal["outsourcing", "internal", "maintenance"] = Field(
        ..., description="프로젝트 유형"
    )
    description: Optional[str] = Field(None, description="설명")
    task_templates: Optional[list[TaskTemplateItem]] = Field(None, description="업무 템플릿")
    schedule_templates: Optional[list[ScheduleTemplateItem]] = Field(None, description="일정 템플릿")


class TemplateUpdate(BaseModel):
    """템플릿 수정"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    task_templates: Optional[list[TaskTemplateItem]] = None
    schedule_templates: Optional[list[ScheduleTemplateItem]] = None


class TemplateResponse(BaseModel):
    """템플릿 응답"""
    id: int
    user_id: int
    team_id: Optional[int] = None
    name: str
    project_type: str
    description: Optional[str] = None
    task_templates: Optional[list[dict]] = None
    schedule_templates: Optional[list[dict]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateListResponse(BaseModel):
    """템플릿 목록 응답"""
    templates: list[TemplateResponse]
    total: int


# ── 반복 업무 ──

class RecurringTaskCreate(BaseModel):
    """반복 업무 설정"""
    task_name: str = Field(..., min_length=1, max_length=300, description="업무명")
    description: Optional[str] = Field(None, description="설명")
    frequency: Literal["daily", "weekly", "monthly"] = Field(..., description="주기")
    day_of_month: Optional[int] = Field(None, ge=1, le=31, description="매월 N일")
    day_of_week: Optional[int] = Field(None, ge=0, le=6, description="요일 (0=월)")
    priority: Literal["긴급", "높음", "보통", "낮음"] = Field(default="보통", description="우선순위")
    assignee_id: Optional[int] = Field(None, description="기본 담당자 ID")


class RecurringTaskUpdate(BaseModel):
    """반복 업무 수정"""
    task_name: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    frequency: Optional[Literal["daily", "weekly", "monthly"]] = None
    day_of_month: Optional[int] = Field(None, ge=1, le=31)
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    priority: Optional[Literal["긴급", "높음", "보통", "낮음"]] = None
    assignee_id: Optional[int] = None
    is_active: Optional[bool] = None


class RecurringTaskResponse(BaseModel):
    """반복 업무 응답"""
    id: int
    project_id: int
    task_name: str
    description: Optional[str] = None
    frequency: str
    day_of_month: Optional[int] = None
    day_of_week: Optional[int] = None
    priority: str
    assignee_id: Optional[int] = None
    is_active: bool
    last_generated_at: Optional[datetime] = None
    created_at: datetime
    assignee_name: Optional[str] = None

    model_config = {"from_attributes": True}
