"""캘린더 연동 서비스 — Phase 6 (§17)

Google Calendar / Outlook 연동.
OAuth code → token 교환, 업무 → 캘린더 이벤트 동기화.
"""
import asyncio
import logging

import httpx
from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import CalendarSync, CalendarEvent, Task, utc_now
from app.services.crypto_service import encrypt_token, decrypt_token

logger = logging.getLogger(__name__)


# ── OAuth 코드 → 토큰 교환 ──

async def _exchange_oauth_code(provider: str, auth_code: str) -> dict:
    """OAuth authorization code → access_token, refresh_token, calendar_id"""
    if provider == "google":
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "code": auth_code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": "postmessage",
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(token_url, data=payload)
            if resp.status_code != 200:
                logger.error(f"Google OAuth 토큰 교환 실패: {resp.text}")
                raise HTTPException(status_code=502, detail="Google 인증에 실패했습니다")
            data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", ""),
            "calendar_id": "primary",
        }
    elif provider == "outlook":
        raise HTTPException(
            status_code=501,
            detail="Outlook 캘린더 연동은 준비 중입니다",
        )
    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 캘린더: {provider}")


# ── 연동 (connect) ──

async def connect_calendar(db: AsyncSession, user, data) -> CalendarSync:
    """캘린더 연동 — OAuth code 교환 + CalendarSync 저장"""
    # 기존 동일 provider 연동 비활성화
    existing = await db.execute(
        select(CalendarSync).where(
            CalendarSync.user_id == user.id,
            CalendarSync.provider == data.provider,
            CalendarSync.is_active == True,  # noqa: E712
        )
    )
    for old in existing.scalars().all():
        old.is_active = False

    # OAuth 토큰 교환
    tokens = await _exchange_oauth_code(data.provider, data.auth_code)

    # 암호화하여 저장
    sync = CalendarSync(
        user_id=user.id,
        provider=data.provider,
        access_token=encrypt_token(tokens["access_token"]),
        refresh_token=encrypt_token(tokens["refresh_token"]),
        calendar_id=tokens["calendar_id"],
    )
    db.add(sync)
    await db.commit()
    await db.refresh(sync)
    return sync


# ── 연동 해제 ──

async def disconnect_calendar(db: AsyncSession, user, sync_id: int):
    """캘린더 연동 해제 — 비활성화 + 이벤트 매핑 삭제"""
    result = await db.execute(
        select(CalendarSync).where(
            CalendarSync.id == sync_id,
            CalendarSync.user_id == user.id,
        )
    )
    sync = result.scalar_one_or_none()
    if not sync:
        raise HTTPException(status_code=404, detail="캘린더 연동을 찾을 수 없습니다")

    sync.is_active = False
    await db.execute(
        delete(CalendarEvent).where(CalendarEvent.calendar_sync_id == sync_id)
    )
    await db.commit()


# ── 동기화 ──

async def sync_tasks_to_calendar(db: AsyncSession, user, sync_id: int) -> int:
    """사용자의 미완료 업무 → 캘린더 이벤트 동기화. 동기화된 건수 반환."""
    result = await db.execute(
        select(CalendarSync).where(
            CalendarSync.id == sync_id,
            CalendarSync.user_id == user.id,
            CalendarSync.is_active == True,  # noqa: E712
        )
    )
    sync = result.scalar_one_or_none()
    if not sync:
        raise HTTPException(status_code=404, detail="활성 캘린더 연동을 찾을 수 없습니다")

    if sync.provider != "google":
        raise HTTPException(status_code=501, detail="현재 Google Calendar만 동기화를 지원합니다")

    # 미완료 + due_date 있는 업무
    tasks_result = await db.execute(
        select(Task).where(
            Task.assignee_id == user.id,
            Task.status.notin_(["completed", "confirmed"]),
            Task.due_date != None,  # noqa: E711
        )
    )
    tasks = tasks_result.scalars().all()

    if not tasks:
        return 0

    # 기존 이벤트 매핑 조회
    events_result = await db.execute(
        select(CalendarEvent).where(CalendarEvent.calendar_sync_id == sync_id)
    )
    existing_events = {e.task_id: e for e in events_result.scalars().all()}

    # Google Calendar API 호출
    access_token = decrypt_token(sync.access_token)
    synced = 0

    for task in tasks:
        event_body = {
            "summary": f"[CS] {task.task_name}",
            "start": {"date": task.due_date},
            "end": {"date": task.due_date},
            "description": task.description or "",
        }

        try:
            existing = existing_events.get(task.id)
            if existing:
                # 기존 이벤트 업데이트
                await _update_calendar_event(
                    access_token, sync.calendar_id, existing.external_event_id, event_body,
                )
                existing.synced_at = utc_now()
            else:
                # 새 이벤트 생성
                event_id = await _create_calendar_event(
                    access_token, sync.calendar_id, event_body,
                )
                if event_id:
                    db.add(CalendarEvent(
                        task_id=task.id,
                        calendar_sync_id=sync_id,
                        external_event_id=event_id,
                    ))
            synced += 1
        except Exception as e:
            logger.warning(f"캘린더 이벤트 동기화 실패 (task {task.id}): {e}")

    sync.last_synced_at = utc_now()
    await db.commit()
    return synced


# ── 상태 조회 ──

async def get_calendar_status(db: AsyncSession, user) -> list[CalendarSync]:
    """사용자의 캘린더 연동 목록"""
    result = await db.execute(
        select(CalendarSync).where(CalendarSync.user_id == user.id)
    )
    return result.scalars().all()


# ── Google Calendar API 헬퍼 ──

async def _create_calendar_event(
    access_token: str, calendar_id: str, event_body: dict,
) -> str | None:
    """Google Calendar에 이벤트 생성 → event_id 반환"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            headers={"Authorization": f"Bearer {access_token}"},
            json=event_body,
        )
        if resp.status_code in (200, 201):
            return resp.json().get("id")
        logger.error(f"Google Calendar 이벤트 생성 실패: {resp.status_code} {resp.text}")
        return None


async def _update_calendar_event(
    access_token: str, calendar_id: str, event_id: str, event_body: dict,
):
    """Google Calendar 이벤트 업데이트"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json=event_body,
        )
        if resp.status_code not in (200, 201):
            logger.warning(f"Google Calendar 이벤트 업데이트 실패: {resp.status_code}")
