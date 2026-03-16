"""4차 개발 Phase 3 — 멤버 간 채팅 API (SSE 기반)"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from pydantic import BaseModel, Field
from typing import Optional
import asyncio
import json
import logging

from app.database import (
    get_db, ChatRoom, ChatRoomMember, RoomMessage,
    TeamMember, User, Notification, utc_now,
)
from app.api.endpoints.auth import require_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

# SSE 메시지 브로커 (in-memory)
_chat_subscribers: dict[int, list[asyncio.Queue]] = {}  # user_id → [Queue, ...]


def _publish_message(user_id: int, data: dict):
    """특정 사용자에게 SSE 메시지 발행"""
    for q in _chat_subscribers.get(user_id, []):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass


# ── Pydantic 모델 ──────────────────────────────

class RoomCreate(BaseModel):
    type: str = Field(..., pattern=r'^(direct|group)$')
    member_ids: list[int] = Field(..., min_length=1)
    name: Optional[str] = Field(None, max_length=200)


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    file_urls: Optional[list] = None


# ── 헬퍼 ──────────────────────────────────────

def _room_to_dict(room: ChatRoom, members: list = None, last_msg: dict = None, unread: int = 0) -> dict:
    return {
        "id": room.id,
        "team_id": room.team_id,
        "name": room.name,
        "type": room.type,
        "project_id": room.project_id,
        "members": members or [],
        "last_message": last_msg,
        "unread_count": unread,
        "created_at": room.created_at.isoformat() if room.created_at else None,
    }


def _message_to_dict(msg: RoomMessage, sender: User = None) -> dict:
    return {
        "id": msg.id,
        "room_id": msg.room_id,
        "sender_id": msg.sender_id,
        "sender_name": sender.name if sender else None,
        "sender_picture": sender.picture if sender else None,
        "content": msg.content,
        "file_urls": msg.file_urls,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


async def _get_room_if_member(db: AsyncSession, room_id: int, user_id: int) -> ChatRoom:
    """채팅방 조회 + 멤버 확인"""
    room = await db.get(ChatRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없습니다.")

    member = await db.execute(
        select(ChatRoomMember).where(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id == user_id,
        )
    )
    if not member.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="채팅방 멤버가 아닙니다.")
    return room


# ── 채팅방 API ─────────────────────────────────

@router.get("/chat/rooms")
async def list_rooms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """내 채팅방 목록"""
    # 내가 참여한 채팅방
    my_rooms = await db.execute(
        select(ChatRoomMember.room_id, ChatRoomMember.last_read_at)
        .where(ChatRoomMember.user_id == current_user.id)
    )
    room_data = {r.room_id: r.last_read_at for r in my_rooms.all()}

    if not room_data:
        return []

    rooms = await db.execute(
        select(ChatRoom).where(ChatRoom.id.in_(room_data.keys()))
    )

    result = []
    for room in rooms.scalars().all():
        # 멤버 목록
        members_q = await db.execute(
            select(ChatRoomMember, User)
            .join(User, ChatRoomMember.user_id == User.id)
            .where(ChatRoomMember.room_id == room.id)
        )
        members = [
            {"user_id": m.user_id, "name": u.name, "picture": u.picture}
            for m, u in members_q.all()
        ]

        # 마지막 메시지
        last_msg_q = await db.execute(
            select(RoomMessage, User)
            .join(User, RoomMessage.sender_id == User.id)
            .where(RoomMessage.room_id == room.id)
            .order_by(desc(RoomMessage.created_at))
            .limit(1)
        )
        last_row = last_msg_q.one_or_none()
        last_msg = _message_to_dict(last_row[0], last_row[1]) if last_row else None

        # 안읽은 메시지 수
        last_read = room_data.get(room.id)
        unread = 0
        if last_read:
            unread_q = await db.execute(
                select(func.count(RoomMessage.id)).where(
                    RoomMessage.room_id == room.id,
                    RoomMessage.created_at > last_read,
                    RoomMessage.sender_id != current_user.id,
                )
            )
            unread = unread_q.scalar() or 0
        else:
            unread_q = await db.execute(
                select(func.count(RoomMessage.id)).where(
                    RoomMessage.room_id == room.id,
                    RoomMessage.sender_id != current_user.id,
                )
            )
            unread = unread_q.scalar() or 0

        # 1:1 채팅방 이름 자동 설정
        display_name = room.name
        if room.type == "direct" and not display_name:
            other = [m for m in members if m["user_id"] != current_user.id]
            display_name = other[0]["name"] if other else "1:1 채팅"

        room_dict = _room_to_dict(room, members, last_msg, unread)
        room_dict["name"] = display_name
        result.append(room_dict)

    # 최근 메시지 순 정렬
    result.sort(
        key=lambda x: x["last_message"]["created_at"] if x["last_message"] else "",
        reverse=True,
    )
    return result


@router.post("/chat/rooms")
async def create_room(
    body: RoomCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """채팅방 생성"""
    all_member_ids = list(set(body.member_ids + [current_user.id]))

    # 1:1 채팅: 기존 채팅방 확인
    if body.type == "direct":
        if len(all_member_ids) != 2:
            raise HTTPException(status_code=400, detail="1:1 채팅은 2명이어야 합니다.")

        # 기존 1:1 채팅방 검색
        existing = await db.execute(
            select(ChatRoom)
            .join(ChatRoomMember, ChatRoom.id == ChatRoomMember.room_id)
            .where(
                ChatRoom.type == "direct",
                ChatRoomMember.user_id == current_user.id,
            )
        )
        for room in existing.scalars().all():
            mem_q = await db.execute(
                select(ChatRoomMember.user_id).where(ChatRoomMember.room_id == room.id)
            )
            member_ids_in_room = {r[0] for r in mem_q.all()}
            if member_ids_in_room == set(all_member_ids):
                return {"id": room.id, "existing": True}

    # 팀 확인 (첫 번째 멤버의 공통 팀 사용)
    team_result = await db.execute(
        select(TeamMember.team_id)
        .where(TeamMember.user_id == current_user.id)
        .limit(1)
    )
    team_row = team_result.scalar_one_or_none()
    if not team_row:
        raise HTTPException(status_code=400, detail="팀에 소속되어 있어야 합니다.")

    room = ChatRoom(
        team_id=team_row,
        name=body.name,
        type=body.type,
    )
    db.add(room)
    await db.flush()

    for uid in all_member_ids:
        db.add(ChatRoomMember(room_id=room.id, user_id=uid))

    await db.commit()
    await db.refresh(room)
    return {"id": room.id, "type": room.type, "name": room.name}


# ── 메시지 API ─────────────────────────────────

@router.get("/chat/rooms/{room_id}/messages")
async def list_messages(
    room_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """메시지 목록 (페이지네이션, 최신 순)"""
    await _get_room_if_member(db, room_id, current_user.id)

    total_q = await db.execute(
        select(func.count(RoomMessage.id)).where(RoomMessage.room_id == room_id)
    )
    total = total_q.scalar() or 0

    result = await db.execute(
        select(RoomMessage, User)
        .join(User, RoomMessage.sender_id == User.id)
        .where(RoomMessage.room_id == room_id)
        .order_by(desc(RoomMessage.created_at))
        .offset((page - 1) * size)
        .limit(size)
    )
    messages = [_message_to_dict(m, u) for m, u in result.all()]
    messages.reverse()  # 오래된 순으로 반환

    return {"items": messages, "total": total, "page": page, "size": size}


@router.post("/chat/rooms/{room_id}/messages")
async def send_message(
    room_id: int,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """메시지 전송"""
    room = await _get_room_if_member(db, room_id, current_user.id)

    msg = RoomMessage(
        room_id=room_id,
        sender_id=current_user.id,
        content=body.content,
        file_urls=body.file_urls,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    msg_dict = _message_to_dict(msg, current_user)

    # SSE 발행: 채팅방 멤버에게
    members_q = await db.execute(
        select(ChatRoomMember.user_id).where(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id != current_user.id,
        )
    )
    for (uid,) in members_q.all():
        _publish_message(uid, {
            "type": "new_message",
            "room_id": room_id,
            "message": msg_dict,
        })

        # 알림 생성
        display_name = room.name or current_user.name or "채팅"
        db.add(Notification(
            user_id=uid,
            type="chat_message",
            title=f"새 메시지 — {display_name}",
            message=f"{current_user.name}: {body.content[:50]}",
            link=f"#/chat/{room_id}",
        ))
    await db.commit()

    return msg_dict


@router.patch("/chat/rooms/{room_id}/read")
async def mark_read(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """읽음 처리"""
    await _get_room_if_member(db, room_id, current_user.id)

    result = await db.execute(
        select(ChatRoomMember).where(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id == current_user.id,
        )
    )
    member = result.scalar_one()
    member.last_read_at = utc_now()
    await db.commit()
    return {"ok": True}


# ── SSE 스트림 ─────────────────────────────────

@router.get("/chat/stream")
async def chat_stream(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """SSE 실시간 메시지 스트림"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    if current_user.id not in _chat_subscribers:
        _chat_subscribers[current_user.id] = []
    _chat_subscribers[current_user.id].append(queue)

    async def event_generator():
        try:
            # 연결 확인
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"

            while True:
                # 클라이언트 연결 종료 감지
                if await request.is_disconnected():
                    break

                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # 하트비트
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        finally:
            try:
                _chat_subscribers.get(current_user.id, []).remove(queue)
            except ValueError:
                pass
            if not _chat_subscribers.get(current_user.id):
                _chat_subscribers.pop(current_user.id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
