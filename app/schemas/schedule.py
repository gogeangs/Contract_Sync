from pydantic import BaseModel, Field
from typing import Optional
from datetime import date
from enum import Enum


class ScheduleType(str, Enum):
    """일정 유형"""

    START = "착수"
    COMPLETION = "완료"
    DESIGN = "설계"
    DEVELOPMENT = "개발"
    TEST = "테스트"
    DELIVERY = "납품"
    INTERIM_REPORT = "중간보고"
    FINAL_REPORT = "최종보고"
    INSPECTION = "검수"
    HANDOVER = "인도"
    OTHER = "기타"


class ScheduleItem(BaseModel):
    """개별 일정 항목"""

    phase: str = Field(..., description="단계명 (예: 1차 설계)")
    schedule_type: str = Field(..., description="일정 유형")
    start_date: Optional[str] = Field(None, description="시작일")
    end_date: Optional[str] = Field(None, description="종료일")
    description: Optional[str] = Field(None, description="상세 설명")
    deliverables: Optional[list[str]] = Field(None, description="산출물 목록")


class ContractSchedule(BaseModel):
    """계약서 추진 일정 전체"""

    contract_name: Optional[str] = Field(None, description="계약명")
    company_name: Optional[str] = Field(None, description="기업명")
    contractor: Optional[str] = Field(None, description="수급자")
    client: Optional[str] = Field(None, description="발주처")
    contract_date: Optional[str] = Field(None, description="계약일")
    contract_start_date: Optional[str] = Field(None, description="착수일")
    contract_end_date: Optional[str] = Field(None, description="완수일")
    total_duration_days: Optional[int] = Field(None, description="총 사업 기간 (일)")
    contract_amount: Optional[str] = Field(None, description="계약 금액")
    payment_method: Optional[str] = Field(None, description="계약금 지급 방식")
    payment_due_date: Optional[str] = Field(None, description="입금예정일")
    schedules: list[ScheduleItem] = Field(default_factory=list, description="단계별 일정 목록")
    milestones: Optional[list[str]] = Field(None, description="주요 마일스톤")


class TaskItem(BaseModel):
    """생성된 업무 항목"""

    task_id: int = Field(..., description="업무 ID")
    task_name: str = Field(..., description="업무명")
    phase: str = Field(..., description="해당 단계")
    due_date: Optional[str] = Field(None, description="마감일")
    priority: str = Field(default="보통", description="우선순위")
    status: str = Field(default="대기", description="상태")


class ScheduleResponse(BaseModel):
    """API 응답"""

    success: bool
    message: str
    contract_schedule: Optional[ContractSchedule] = None
    task_list: Optional[list[TaskItem]] = None
    raw_text_preview: Optional[str] = Field(None, description="추출된 텍스트 미리보기")
    raw_text: Optional[str] = Field(None, description="추출된 전체 텍스트")
