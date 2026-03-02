from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class TaskCreate(BaseModel):
    """업무 생성"""
    task_name: str = Field(..., min_length=1, max_length=300, description="업무명")
    project_id: Optional[int] = Field(None, description="소속 프로젝트")
    description: Optional[str] = Field(None, description="상세 설명")
    phase: Optional[str] = Field(None, max_length=200, description="단계명")
    priority: Literal["긴급", "높음", "보통", "낮음"] = Field(default="보통", description="우선순위")
    due_date: Optional[str] = Field(None, description="마감일 (YYYY-MM-DD)")
    start_date: Optional[str] = Field(None, description="시작일 (YYYY-MM-DD)")
    assignee_id: Optional[int] = Field(None, description="담당자 ID")
    is_client_facing: bool = Field(default=False, description="발주처 대면 업무 여부")


class TaskUpdate(BaseModel):
    """업무 수정"""
    task_name: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    phase: Optional[str] = Field(None, max_length=200)
    priority: Optional[Literal["긴급", "높음", "보통", "낮음"]] = None
    due_date: Optional[str] = None
    start_date: Optional[str] = None
    is_client_facing: Optional[bool] = None


class TaskStatusUpdate(BaseModel):
    """업무 상태 변경"""
    status: str = Field(
        ...,
        pattern=r"^(pending|in_progress|completed|report_sent|feedback_pending|confirmed|revision_requested)$",
        description="업무 상태",
    )


class TaskAssigneeUpdate(BaseModel):
    """담당자 변경"""
    assignee_id: Optional[int] = Field(None, description="담당자 ID (null이면 해제)")


class TaskNoteUpdate(BaseModel):
    """처리 내용 메모 저장"""
    note: str = Field(..., max_length=5000, description="처리 내용")


class TaskMoveRequest(BaseModel):
    """프로젝트 이동"""
    project_id: Optional[int] = Field(None, description="이동 대상 프로젝트 ID (null이면 프로젝트 해제)")


class TaskReorderRequest(BaseModel):
    """업무 순서 변경 (벌크)"""
    task_orders: list[dict] = Field(
        ..., description="[{task_id: int, sort_order: int}, ...]"
    )


class TaskResponse(BaseModel):
    """업무 응답"""
    id: int
    task_code: Optional[str] = None
    project_id: Optional[int] = None
    user_id: int
    team_id: Optional[int] = None
    task_name: str
    description: Optional[str] = None
    phase: Optional[str] = None
    status: str
    priority: str
    due_date: Optional[str] = None
    start_date: Optional[str] = None
    assignee_id: Optional[int] = None
    is_client_facing: bool = False
    note: Optional[str] = None
    sort_order: int = 0
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # 집계/조인 필드
    assignee_name: Optional[str] = None
    project_name: Optional[str] = None
    attachment_count: int = 0

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    """업무 목록 응답"""
    tasks: list[TaskResponse]
    total: int


class TaskAttachmentResponse(BaseModel):
    """산출물 응답"""
    id: int
    task_id: int
    file_name: str
    file_size: int
    mime_type: str
    uploaded_by: Optional[int] = None
    uploader_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
