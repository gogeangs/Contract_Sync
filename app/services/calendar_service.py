"""캘린더 연동 서비스 — Phase 6 (§17) + 5차 확장

Google Calendar 연동.
OAuth code → token 교환, 토큰 자동 갱신, 양방향 동기화.
sync_direction: cs_to_google / google_to_cs / bidirectional
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import CalendarSync, CalendarEvent, Task, utc_now
from app.services.crypto_service import encrypt_token, decrypt_token

logger = logging.getLogger(__name__)

VALID_SYNC_DIRECTIONS = {"cs_to_google", "google_to_cs", "bidirectional"}


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


# ── 토큰 자동 갱신 ──

async def _refresh_access_token(sync: CalendarSync, db: AsyncSession) -> str:
    """refresh_token으로 access_token 재발급. 갱신된 토큰을 DB에 저장."""
    if not sync.refresh_token:
        raise HTTPException(status_code=401, detail="갱신 토큰이 없습니다. 캘린더를 다시 연동해주세요.")

    refresh_tok = decrypt_token(sync.refresh_token)
    payload = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": refresh_tok,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post("https://oauth2.googleapis.com/token", data=payload)
        if resp.status_code != 200:
            logger.error(f"Google 토큰 갱신 실패: {resp.text}")
            raise HTTPException(status_code=502, detail="Google 토큰 갱신에 실패했습니다. 캘린더를 다시 연동해주세요.")
        data = resp.json()

    new_access = data["access_token"]
    sync.access_token = encrypt_token(new_access)
    # refresh_token은 구글이 새로 주는 경우에만 갱신
    if data.get("refresh_token"):
        sync.refresh_token = encrypt_token(data["refresh_token"])
    await db.flush()
    return new_access


async def _get_valid_access_token(sync: CalendarSync, db: AsyncSession) -> str:
    """유효한 access_token 반환. 만료 시 자동 갱신 시도."""
    if not sync.access_token:
        return await _refresh_access_token(sync, db)
    access_token = decrypt_token(sync.access_token)
    # 토큰 유효성 간단 확인 (Google Calendar API 호출)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"https://www.googleapis.com/calendar/v3/calendars/{sync.calendar_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code == 401:
        # 토큰 만료 → 갱신
        access_token = await _refresh_access_token(sync, db)
    return access_token


# ── 연동 (connect) ──

async def connect_calendar(
    db: AsyncSession, user, data, sync_direction: str = "cs_to_google",
) -> CalendarSync:
    """캘린더 연동 — OAuth code 교환 + CalendarSync 저장"""
    if sync_direction not in VALID_SYNC_DIRECTIONS:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 동기화 방향: {sync_direction}")

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
        sync_direction=sync_direction,
    )
    db.add(sync)
    await db.commit()
    await db.refresh(sync)
    return sync


# ── 동기화 방향 변경 ──

async def update_sync_direction(
    db: AsyncSession, user, sync_id: int, sync_direction: str,
) -> CalendarSync:
    """동기화 방향 변경"""
    if sync_direction not in VALID_SYNC_DIRECTIONS:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 동기화 방향: {sync_direction}")

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

    sync.sync_direction = sync_direction
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


# ── CS → Google 동기화 ──

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

    if sync.sync_direction == "google_to_cs":
        raise HTTPException(status_code=400, detail="동기화 방향이 'Google→CS'로 설정되어 있습니다. CS→Google 동기화를 수행하려면 방향을 변경해주세요.")

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
    access_token = await _get_valid_access_token(sync, db)
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


# ── Google → CS 동기화 ──

async def sync_calendar_to_tasks(db: AsyncSession, user, sync_id: int) -> dict:
    """Google Calendar 이벤트 → CS 업무로 가져오기. 생성/업데이트 건수 반환."""
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

    if sync.sync_direction == "cs_to_google":
        raise HTTPException(status_code=400, detail="동기화 방향이 'CS→Google'로 설정되어 있습니다. Google→CS 동기화를 수행하려면 방향을 변경해주세요.")

    access_token = await _get_valid_access_token(sync, db)

    # Google Calendar에서 향후 30일 이벤트 조회
    now = datetime.now(timezone.utc)
    time_min = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max = (now + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    events = await _list_calendar_events(access_token, sync.calendar_id, time_min, time_max)

    # 기존 매핑 조회
    mapping_result = await db.execute(
        select(CalendarEvent).where(CalendarEvent.calendar_sync_id == sync_id)
    )
    existing_by_external = {e.external_event_id: e for e in mapping_result.scalars().all()}

    # 사용자의 기본 팀 조회 (업무 생성용)
    from app.database import TeamMember
    team_result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id).limit(1)
    )
    team_row = team_result.first()
    team_id = team_row[0] if team_row else None

    created = 0
    updated = 0

    for ev in events:
        event_id = ev.get("id", "")
        summary = ev.get("summary", "")

        # [CS] 접두사가 붙은 이벤트는 CS에서 생성한 것 → 스킵
        if summary.startswith("[CS] "):
            continue

        # 날짜 추출
        start = ev.get("start", {})
        due_date = start.get("date") or (start.get("dateTime", "")[:10] if start.get("dateTime") else None)

        if not due_date:
            continue

        existing_mapping = existing_by_external.get(event_id)
        if existing_mapping:
            # 기존 매핑 → 업무 업데이트
            task = await db.get(Task, existing_mapping.task_id)
            if task:
                task.task_name = summary
                task.due_date = due_date
                task.description = ev.get("description", "") or task.description
                existing_mapping.synced_at = utc_now()
                updated += 1
        else:
            # 새 이벤트 → 업무 생성
            new_task = Task(
                task_name=summary,
                due_date=due_date,
                description=ev.get("description", ""),
                user_id=user.id,
                team_id=team_id,
                assignee_id=user.id,
                status="pending",
                priority="보통",
                source="google_calendar",
            )
            db.add(new_task)
            await db.flush()

            db.add(CalendarEvent(
                task_id=new_task.id,
                calendar_sync_id=sync_id,
                external_event_id=event_id,
            ))
            created += 1

    sync.last_synced_at = utc_now()
    await db.commit()
    return {"created": created, "updated": updated}


# ── 통합 동기화 (방향 자동 판별) ──

async def sync_calendar(db: AsyncSession, user, sync_id: int) -> dict:
    """sync_direction에 따라 적절한 동기화 수행.
    bidirectional일 때는 방향 체크를 건너뛰고 CS→Google + Google→CS를 순차 호출.
    """
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

    direction = sync.sync_direction or "cs_to_google"

    if direction == "cs_to_google":
        count = await sync_tasks_to_calendar(db, user, sync_id)
        return {"direction": direction, "cs_to_google": count}
    elif direction == "google_to_cs":
        g2c = await sync_calendar_to_tasks(db, user, sync_id)
        return {"direction": direction, **g2c}
    elif direction == "bidirectional":
        # 양방향: 방향 체크를 건너뛰기 위해 임시로 각 방향 설정 후 호출
        # sync_tasks_to_calendar / sync_calendar_to_tasks 내부에서 방향 검증이 있으므로
        # 직접 로직을 인라인으로 수행
        if sync.provider != "google":
            raise HTTPException(status_code=501, detail="현재 Google Calendar만 동기화를 지원합니다")

        access_token = await _get_valid_access_token(sync, db)

        # ── Phase A: CS → Google ──
        tasks_result = await db.execute(
            select(Task).where(
                Task.assignee_id == user.id,
                Task.status.notin_(["completed", "confirmed"]),
                Task.due_date != None,  # noqa: E711
            )
        )
        tasks = tasks_result.scalars().all()

        events_result = await db.execute(
            select(CalendarEvent).where(CalendarEvent.calendar_sync_id == sync_id)
        )
        existing_events = {e.task_id: e for e in events_result.scalars().all()}

        cs_to_google_count = 0
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
                    await _update_calendar_event(
                        access_token, sync.calendar_id, existing.external_event_id, event_body,
                    )
                    existing.synced_at = utc_now()
                else:
                    eid = await _create_calendar_event(access_token, sync.calendar_id, event_body)
                    if eid:
                        db.add(CalendarEvent(
                            task_id=task.id, calendar_sync_id=sync_id, external_event_id=eid,
                        ))
                cs_to_google_count += 1
            except Exception as e:
                logger.warning(f"양방향 CS→Google 실패 (task {task.id}): {e}")

        # ── Phase B: Google → CS ──
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        time_min = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        time_max = (now + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        events = await _list_calendar_events(access_token, sync.calendar_id, time_min, time_max)

        mapping_result = await db.execute(
            select(CalendarEvent).where(CalendarEvent.calendar_sync_id == sync_id)
        )
        existing_by_external = {e.external_event_id: e for e in mapping_result.scalars().all()}

        from app.database import TeamMember
        team_result = await db.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == user.id).limit(1)
        )
        team_row = team_result.first()
        team_id = team_row[0] if team_row else None

        g2c_created = 0
        g2c_updated = 0
        for ev in events:
            event_id = ev.get("id", "")
            summary = ev.get("summary", "")
            if summary.startswith("[CS] "):
                continue
            start = ev.get("start", {})
            due_date = start.get("date") or (start.get("dateTime", "")[:10] if start.get("dateTime") else None)
            if not due_date:
                continue
            existing_mapping = existing_by_external.get(event_id)
            if existing_mapping:
                task = await db.get(Task, existing_mapping.task_id)
                if task:
                    task.task_name = summary
                    task.due_date = due_date
                    task.description = ev.get("description", "") or task.description
                    existing_mapping.synced_at = utc_now()
                    g2c_updated += 1
            else:
                new_task = Task(
                    task_name=summary, due_date=due_date,
                    description=ev.get("description", ""),
                    user_id=user.id, team_id=team_id, assignee_id=user.id,
                    status="pending", priority="보통", source="google_calendar",
                )
                db.add(new_task)
                await db.flush()
                db.add(CalendarEvent(
                    task_id=new_task.id, calendar_sync_id=sync_id, external_event_id=event_id,
                ))
                g2c_created += 1

        sync.last_synced_at = utc_now()
        await db.commit()
        return {
            "direction": direction,
            "cs_to_google": cs_to_google_count,
            "google_to_cs_created": g2c_created,
            "google_to_cs_updated": g2c_updated,
        }
    else:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 동기화 방향: {direction}")


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


async def _list_calendar_events(
    access_token: str, calendar_id: str, time_min: str, time_max: str,
) -> list[dict]:
    """Google Calendar에서 지정 기간의 이벤트 목록 조회"""
    events = []
    page_token = None
    max_pages = 10  # 안전장치: 최대 1000건

    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(max_pages):
            params = {
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 100,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await client.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            if resp.status_code != 200:
                logger.error(f"Google Calendar 이벤트 조회 실패: {resp.status_code} {resp.text}")
                break

            data = resp.json()
            events.extend(data.get("items", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

    return events
