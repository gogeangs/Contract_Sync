from pydantic import BaseModel, Field
from typing import Optional


class DashboardSummary(BaseModel):
    """대시보드 통계"""
    active_projects: int = 0
    pending_tasks: int = 0
    in_progress_tasks: int = 0
    monthly_revenue: int = 0
    outstanding_amount: int = 0
    feedback_pending_tasks: int = 0


class RevenueData(BaseModel):
    """매출 추이"""
    months: list[str] = Field(default_factory=list)
    amounts: list[int] = Field(default_factory=list)


class WorkloadItem(BaseModel):
    """팀 워크로드"""
    user_id: int
    user_name: str
    task_count: int
    completed_count: int


class AIInsight(BaseModel):
    """AI 인사이트"""
    type: str  # warning / info / suggestion
    message: str
    related_id: Optional[int] = None
    related_type: Optional[str] = None
