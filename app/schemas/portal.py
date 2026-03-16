from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PortalTokenCreate(BaseModel):
    """포털 토큰 발급"""
    expires_at: Optional[datetime] = Field(None, description="만료일 (미지정 시 프로젝트 종료일 + 30일)")


class PortalTokenResponse(BaseModel):
    """포털 토큰 응답"""
    id: int
    client_id: int
    project_id: int
    token: str
    portal_url: str
    expires_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PortalDataResponse(BaseModel):
    """포털 데이터 응답 (비로그인 조회)"""
    project_name: str
    project_type: str
    status: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    progress_percent: float = 0.0
    client_name: Optional[str] = None
    tasks: list[dict] = Field(default_factory=list)
    pending_feedbacks: list[dict] = Field(default_factory=list)
    reports: list[dict] = Field(default_factory=list)


class CalendarConnectRequest(BaseModel):
    """캘린더 연동 요청"""
    provider: str = Field(..., pattern=r"^(google|outlook)$", description="제공자")
    auth_code: str = Field(..., description="OAuth 인증 코드")
    sync_direction: str = Field(
        "cs_to_google",
        pattern=r"^(cs_to_google|google_to_cs|bidirectional)$",
        description="동기화 방향: cs_to_google / google_to_cs / bidirectional",
    )


class CalendarSyncDirectionRequest(BaseModel):
    """동기화 방향 변경 요청"""
    sync_direction: str = Field(
        ...,
        pattern=r"^(cs_to_google|google_to_cs|bidirectional)$",
        description="동기화 방향",
    )


class CalendarStatusResponse(BaseModel):
    """캘린더 연동 상태"""
    id: int
    provider: str
    calendar_id: str
    sync_direction: Optional[str] = "cs_to_google"
    is_active: bool
    last_synced_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
