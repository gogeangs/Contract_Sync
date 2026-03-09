"""고객 피드백 포털 + 피드백 요청 관리 API — 3차 개발 S4-1 ~ S4-4

POST /projects/{id}/feedback-request — 피드백 요청 생성
GET /feedback/portal/{token} — 고객 포털 (비로그인)
POST /feedback/portal/{token}/response — 고객 피드백 제출
GET /feedback/requests — 피드백 요청 목록 (PM용)
GET /feedback/requests/{id} — 피드백 요청 상세
PATCH /feedback/requests/{id}/cancel — 피드백 요청 취소
"""
from fastapi import APIRouter, Request, Query, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.auth import require_current_user
from app.database import get_db
from app.limiter import limiter
from app.services.feedback_request_service import (
    create_feedback_request,
    get_portal_data,
    submit_feedback_response,
    list_feedback_requests,
    get_feedback_request_detail,
    cancel_feedback_request,
)

router = APIRouter()


# ── Schemas ──

class FeedbackRequestCreate(BaseModel):
    recipient_email: str = Field(..., min_length=3, max_length=200)
    subject: str = Field(..., min_length=1, max_length=500)
    message: str | None = Field(None, max_length=2000)
    figma_url: str | None = Field(None, max_length=500)
    feedback_deadline: str | None = Field(None, max_length=10)  # YYYY-MM-DD
    attachments: list | None = None


class FeedbackSubmit(BaseModel):
    response_type: str = Field(..., pattern="^(approved|revision_requested|comment)$")
    content: str | None = Field(None, max_length=5000)
    client_name: str | None = Field(None, max_length=100)
    client_phone: str | None = Field(None, max_length=20)


# ── PM 측 API ──

@router.post("/projects/{project_id}/feedback-request")
@limiter.limit("10/minute")
async def create_request(
    project_id: int,
    data: FeedbackRequestCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """피드백 요청 생성 + 이메일 발송"""
    user = await require_current_user(request, db)
    fb_req = await create_feedback_request(
        db, user, project_id,
        recipient_email=data.recipient_email,
        subject=data.subject,
        message=data.message,
        figma_url=data.figma_url,
        feedback_deadline=data.feedback_deadline,
        attachments=data.attachments,
    )
    return {
        "message": "피드백 요청이 발송되었습니다.",
        "id": fb_req.id,
        "feedback_token": fb_req.feedback_token,
    }


@router.get("/feedback/requests")
@limiter.limit("30/minute")
async def list_requests(
    request: Request,
    project_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """내가 보낸 피드백 요청 목록"""
    user = await require_current_user(request, db)
    return await list_feedback_requests(db, user.id, project_id)


@router.get("/feedback/requests/{request_id}")
@limiter.limit("30/minute")
async def get_request_detail(
    request_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """피드백 요청 상세 (응답 포함)"""
    user = await require_current_user(request, db)
    detail = await get_feedback_request_detail(db, request_id, user.id)
    if not detail:
        raise HTTPException(status_code=404, detail="피드백 요청을 찾을 수 없습니다.")
    return detail


@router.patch("/feedback/requests/{request_id}/cancel")
@limiter.limit("10/minute")
async def cancel_request(
    request_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """피드백 요청 취소 (리마인더 중단)"""
    user = await require_current_user(request, db)
    if not await cancel_feedback_request(db, request_id, user.id):
        raise HTTPException(status_code=400, detail="취소할 수 없습니다.")
    return {"message": "피드백 요청이 취소되었습니다."}


# ── 고객 포털 API (비로그인) ──

@router.get("/feedback/portal/{token}")
async def portal_view(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """고객 피드백 포털 데이터 조회 (비로그인)"""
    data = await get_portal_data(db, token)
    if not data:
        raise HTTPException(status_code=404, detail="유효하지 않은 링크입니다.")
    if "error" in data:
        raise HTTPException(status_code=410, detail=data["error"])
    return data


@router.post("/feedback/portal/{token}/response")
@limiter.limit("5/minute")
async def portal_submit(
    token: str,
    data: FeedbackSubmit,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """고객 피드백 제출 (비로그인)"""
    ip_address = request.client.host if request.client else None
    fb_response = await submit_feedback_response(
        db, token,
        response_type=data.response_type,
        content=data.content,
        client_name=data.client_name,
        client_phone=data.client_phone,
        ip_address=ip_address,
    )
    return {
        "message": "피드백이 접수되었습니다. 감사합니다.",
        "response_type": fb_response.response_type,
    }
