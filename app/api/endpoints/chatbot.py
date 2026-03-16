"""AI 챗봇 API — 3차 개발 S1-6, S1-7

POST /chatbot/message — SSE 스트리밍 응답
GET /chatbot/history — 대화 이력 조회
GET /chatbot/presets — 빠른 질문 프리셋
DELETE /chatbot/sessions/{session_id} — 세션 삭제
"""
from fastapi import APIRouter, Request, Query, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.auth import require_current_user
from app.database import get_db
from app.limiter import limiter
from app.services.chatbot_service import (
    stream_chatbot_response,
    get_chat_history,
    delete_chat_session,
    get_presets_for_user,
    get_user_team_roles,
)

router = APIRouter(prefix="/chatbot")


class ChatContext(BaseModel):
    page: str | None = Field(None, description="현재 페이지 (예: projectDetail, tasks, dashboard)")
    params: dict | None = Field(None, description="페이지 파라미터 (예: {id: 5})")


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    chat_session_id: int | None = Field(None)
    context: ChatContext | None = Field(None, description="현재 화면 맥락")


@router.post("/message")
@limiter.limit("20/minute")
async def send_message(
    data: ChatMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """챗봇 메시지 전송 — SSE 스트리밍 응답"""
    user = await require_current_user(request, db)

    # 화면 맥락 딕셔너리로 전달
    page_context = None
    if data.context:
        page_context = {
            "page": data.context.page,
            "params": data.context.params or {},
        }

    async def event_stream():
        async for event in stream_chatbot_response(
            db, user, data.message, data.chat_session_id,
            page_context=page_context,
        ):
            yield event

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history")
@limiter.limit("30/minute")
async def chat_history(
    request: Request,
    session_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """대화 이력 조회"""
    user = await require_current_user(request, db)
    return await get_chat_history(db, user.id, session_id, limit)


@router.delete("/sessions/{session_id}")
@limiter.limit("10/minute")
async def delete_session(
    session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """대화 세션 삭제"""
    user = await require_current_user(request, db)
    deleted = await delete_chat_session(db, user.id, session_id)
    if not deleted:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return {"message": "세션이 삭제되었습니다."}


@router.get("/presets")
@limiter.limit("30/minute")
async def get_presets(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """빠른 질문 프리셋 조회 (P-2)"""
    user = await require_current_user(request, db)
    team_roles = await get_user_team_roles(db, user.id)
    presets = get_presets_for_user(team_roles)
    return {"presets": presets}
