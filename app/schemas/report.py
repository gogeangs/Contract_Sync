from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── 완료 보고 ──

class CompletionReportCreate(BaseModel):
    """완료 보고 작성"""
    recipient_email: str = Field(..., max_length=200, description="수신자 이메일")
    cc_emails: Optional[list[str]] = Field(None, description="참조 이메일 목록")
    subject: str = Field(..., min_length=1, max_length=500, description="제목")
    body_html: str = Field(..., min_length=1, description="이메일 본문 (HTML)")
    scheduled_at: Optional[datetime] = Field(None, description="예약 발송 시간 (없으면 즉시 발송)")


class CompletionReportUpdate(BaseModel):
    """완료 보고 수정 (예약 상태만 가능)"""
    recipient_email: Optional[str] = Field(None, max_length=200)
    cc_emails: Optional[list[str]] = None
    subject: Optional[str] = Field(None, max_length=500)
    body_html: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class CompletionReportResponse(BaseModel):
    """완료 보고 응답"""
    id: int
    task_id: int
    project_id: int
    sender_id: int
    recipient_email: str
    cc_emails: Optional[list[str]] = None
    subject: str
    body_html: str
    attachments: Optional[list[dict]] = None
    feedback_token: Optional[str] = None
    status: str
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    created_at: datetime
    sender_name: Optional[str] = None
    task_name: Optional[str] = None

    model_config = {"from_attributes": True}


# ── 클라이언트 피드백 ──

class FeedbackSubmit(BaseModel):
    """피드백 제출 (비로그인)"""
    feedback_type: str = Field(
        ...,
        pattern=r"^(confirmed|revision|comment)$",
        description="피드백 유형",
    )
    content: Optional[str] = Field(None, max_length=5000, description="피드백 내용")
    client_name: Optional[str] = Field(None, max_length=100, description="작성자명")


class FeedbackResponse(BaseModel):
    """피드백 응답"""
    id: int
    completion_report_id: int
    task_id: int
    feedback_type: str
    content: Optional[str] = None
    client_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── AI 보고서 ──

class AIReportGenerate(BaseModel):
    """AI 보고서 수동 생성"""
    report_type: str = Field(
        ...,
        pattern=r"^(periodic|completion)$",
        description="보고서 유형",
    )
    period_start: Optional[str] = Field(None, description="대상 기간 시작 (YYYY-MM-DD)")
    period_end: Optional[str] = Field(None, description="대상 기간 종료 (YYYY-MM-DD)")


class AIReportUpdate(BaseModel):
    """AI 보고서 편집"""
    title: Optional[str] = Field(None, max_length=300)
    content_html: Optional[str] = None


class AIReportSend(BaseModel):
    """AI 보고서 발송"""
    recipient_emails: list[str] = Field(..., min_length=1, description="발송 대상 이메일 목록")


class AIReportResponse(BaseModel):
    """AI 보고서 응답"""
    id: int
    project_id: int
    report_type: str
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    title: str
    content_html: str
    content_json: Optional[dict] = None
    status: str
    sent_to: Optional[list[str]] = None
    sent_at: Optional[datetime] = None
    created_at: datetime
    project_name: Optional[str] = None

    model_config = {"from_attributes": True}


class AIReportListResponse(BaseModel):
    """AI 보고서 목록 응답"""
    reports: list[AIReportResponse]
    total: int
