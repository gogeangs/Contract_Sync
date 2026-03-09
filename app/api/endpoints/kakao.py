"""카카오 알림톡 API — 3차 개발 S6-3, S6-5 (선택)

POST /kakao/send — 알림톡 발송
GET /kakao/history — 발송 이력 조회
GET /kakao/templates — 템플릿 목록
"""
from fastapi import APIRouter, Request, Query, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.auth import require_current_user
from app.database import get_db
from app.limiter import limiter
from app.services.kakao_service import (
    send_kakao_notification,
    get_notification_history,
    TEMPLATES,
)

router = APIRouter(prefix="/kakao")


class KakaoSendRequest(BaseModel):
    template_key: str = Field(..., min_length=1)
    recipient_phone: str = Field(..., min_length=10, max_length=20)
    variables: dict = Field(default_factory=dict)
    project_id: int | None = None
    feedback_request_id: int | None = None


@router.post("/send")
@limiter.limit("10/minute")
async def send_notification(
    data: KakaoSendRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """알림톡 발송"""
    await require_current_user(request, db)

    if data.template_key not in TEMPLATES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 템플릿: {data.template_key}")

    record = await send_kakao_notification(
        db,
        template_key=data.template_key,
        recipient_phone=data.recipient_phone,
        variables=data.variables,
        project_id=data.project_id,
        feedback_request_id=data.feedback_request_id,
    )
    await db.commit()

    return {
        "message": "알림톡 발송이 처리되었습니다.",
        "id": record.id,
        "status": record.status,
    }


@router.get("/history")
@limiter.limit("30/minute")
async def history(
    request: Request,
    project_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """알림톡 발송 이력 조회"""
    await require_current_user(request, db)
    records = await get_notification_history(db, project_id, limit)
    return {"history": records}


@router.get("/templates")
@limiter.limit("30/minute")
async def template_list(request: Request, db: AsyncSession = Depends(get_db)):
    """알림톡 템플릿 목록"""
    await require_current_user(request, db)
    return {
        "templates": [
            {"key": k, "code": v["code"], "title": v["title"], "body": v["body"]}
            for k, v in TEMPLATES.items()
        ]
    }
