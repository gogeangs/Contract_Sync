from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── 문서 ──

class DocumentCreate(BaseModel):
    """문서 업로드 시 메타데이터"""
    document_type: str = Field(..., pattern=r"^(estimate|contract|proposal|other)$", description="문서 유형")
    title: str = Field(..., min_length=1, max_length=300, description="문서 제목")


class DocumentUpdate(BaseModel):
    """문서 정보 수정"""
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    document_type: Optional[str] = Field(None, pattern=r"^(estimate|contract|proposal|other)$")


class DocumentStatusUpdate(BaseModel):
    """문서 상태 변경"""
    status: str = Field(..., pattern=r"^(uploaded|analyzing|review_pending|revision_requested|confirmed)$")


class DocumentResponse(BaseModel):
    """문서 응답"""
    id: int
    project_id: int
    user_id: int
    document_type: str
    title: str
    file_name: Optional[str] = None
    stored_path: Optional[str] = None
    status: str
    version: int
    parent_id: Optional[int] = None
    ai_analysis: Optional[dict] = None
    google_sheet_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    uploader_name: Optional[str] = None
    review_count: int = 0

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    """문서 목록 응답"""
    documents: list[DocumentResponse]
    total: int


# ── 문서에서 업무 생성 ──

class GenerateTasksRequest(BaseModel):
    """AI 분석 결과에서 업무 생성 요청"""
    selected_task_indices: list[int] = Field(..., description="선택한 업무 인덱스 목록")


# ── 검토 ──

class ReviewCreate(BaseModel):
    """검토자 지정"""
    reviewer_id: int = Field(..., description="검토자 사용자 ID")


class ReviewSubmit(BaseModel):
    """검토 결과 제출"""
    status: str = Field(..., pattern=r"^(approved|rejected|commented)$", description="검토 결과")
    comment: Optional[str] = Field(None, max_length=5000, description="검토 코멘트")


class ReviewResponse(BaseModel):
    """검토 응답"""
    id: int
    document_id: int
    reviewer_id: int
    reviewer_name: Optional[str] = None
    reviewer_email: Optional[str] = None
    status: str
    comment: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Google Sheets ──

class SheetLinkRequest(BaseModel):
    """기존 Google Sheet 연결"""
    sheet_url: str = Field(..., description="Google Sheets URL")
    title: Optional[str] = Field(None, max_length=300, description="문서 제목 (미입력시 시트명 사용)")


class SheetCreateRequest(BaseModel):
    """새 Google Sheet 생성"""
    title: str = Field(..., min_length=1, max_length=300, description="견적서 제목")


class SheetParseResponse(BaseModel):
    """Google Sheet AI 파싱 결과"""
    estimate_items: list[dict] = Field(default_factory=list)
    total_amount: Optional[float] = None
    estimated_duration_days: Optional[int] = None


# ── AI 핵심 조항 ──

class AIHighlightsResponse(BaseModel):
    """AI 핵심 조항 분석 결과"""
    key_terms: list[dict] = Field(default_factory=list)
    summary: Optional[str] = None
