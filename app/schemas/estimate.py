from pydantic import BaseModel, Field
from typing import Optional


class EstimateItem(BaseModel):
    """견적 항목"""
    name: str = Field(..., description="항목명")
    description: str | None = Field(None, description="항목 설명")
    quantity: int = Field(1, ge=1, description="수량")
    unit: str = Field("식", description="단위")
    unit_price: int = Field(..., gt=0, description="단가")
    amount: int = Field(..., gt=0, description="금액")
    estimated_days: int = Field(..., ge=0, description="예상 소요일")


class EstimateGenerateRequest(BaseModel):
    """AI 견적 생성 요청"""
    project_type: str = Field(
        ..., description="프로젝트 유형 (outsourcing|internal)"
    )
    scope_description: str = Field(
        ..., min_length=10, max_length=1000, description="프로젝트 범위 설명"
    )


class EstimateResponse(BaseModel):
    """AI 견적 생성 응답"""
    items: list[EstimateItem]
    total_amount: int
    estimated_duration_days: int
    notes: str | None = None
    reference_projects: list[str] = []


class EstimateExportRequest(BaseModel):
    """견적서 Google Sheet 내보내기 요청"""
    project_id: int
    title: str = Field("AI 견적서", max_length=200)
    estimate_data: EstimateResponse


class EstimateExportResponse(BaseModel):
    """견적서 Google Sheet 내보내기 응답"""
    document_id: int
    google_sheet_id: str
    sheet_url: str
