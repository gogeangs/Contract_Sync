"""실시간 알림 SSE — 2차 개발 #4

GET /sse/notifications
- 쿠키 인증
- 5초 DB 폴링으로 새 알림 전송
- 30초 heartbeat
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.database import async_session, UserSession, Notification, utc_now

logger = logging.getLogger(__name__)

router = APIRouter()

POLL_INTERVAL = 5   # 초
HEARTBEAT_INTERVAL = 30  # 초


async def _get_user_id_from_cookie(session_token: str) -> int | None:
    """세션 토큰으로 user_id 조회"""
    if not session_token:
        return None
    async with async_session() as db:
        result = await db.execute(
            select(UserSession).where(UserSession.token == session_token)
        )
        session = result.scalar_one_or_none()
        if not session or session.expires_at < utc_now():
            return None
        return session.user_id


async def _event_generator(user_id: int):
    """SSE 이벤트 생성기 — 5초 폴링, 30초 heartbeat"""
    last_check = utc_now()
    heartbeat_counter = 0

    # 초기 연결 확인 이벤트
    yield f"event: connected\ndata: {{\"user_id\": {user_id}}}\n\n"

    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL)
            heartbeat_counter += POLL_INTERVAL

            # 새 알림 조회
            async with async_session() as db:
                result = await db.execute(
                    select(Notification).where(
                        Notification.user_id == user_id,
                        Notification.is_read == False,  # noqa: E712
                        Notification.created_at > last_check,
                    ).order_by(Notification.created_at)
                )
                new_notifications = result.scalars().all()

            now = utc_now()

            for notif in new_notifications:
                data = {
                    "id": notif.id,
                    "type": notif.type,
                    "title": notif.title,
                    "message": notif.message,
                    "link": notif.link,
                    "created_at": notif.created_at.isoformat() if notif.created_at else None,
                }
                yield f"event: notification\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

            last_check = now

            # heartbeat
            if heartbeat_counter >= HEARTBEAT_INTERVAL:
                heartbeat_counter = 0
                ts = now.isoformat() + "Z"
                yield f"event: heartbeat\ndata: {{\"ts\": \"{ts}\"}}\n\n"

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"SSE 이벤트 생성 오류: {e}")
            break


@router.get("/sse/notifications")
async def sse_notifications(request: Request):
    """SSE 알림 스트림"""
    session_token = request.cookies.get("session_token")
    user_id = await _get_user_id_from_cookie(session_token)

    if not user_id:
        return StreamingResponse(
            iter(["event: error\ndata: {\"detail\": \"로그인이 필요합니다\"}\n\n"]),
            media_type="text/event-stream",
            status_code=401,
        )

    async def stream():
        try:
            async for event in _event_generator(user_id):
                if await request.is_disconnected():
                    break
                yield event
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
