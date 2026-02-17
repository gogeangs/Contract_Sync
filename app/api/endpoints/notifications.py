from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, update
from typing import Optional
import logging

from app.database import get_db, Notification, utc_now
from app.api.endpoints.auth import require_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_notifications(
    request: Request,
    unread_only: bool = Query(False, description="읽지 않은 알림만"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """내 알림 목록"""
    user = await require_current_user(request, db)

    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))

    # 전체 개수
    count_q = select(func.count()).select_from(Notification).where(Notification.user_id == user.id)
    if unread_only:
        count_q = count_q.where(Notification.is_read.is_(False))
    total = (await db.execute(count_q)).scalar()

    # 읽지 않은 알림 수
    unread_count = (await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
        )
    )).scalar()

    # 페이지네이션
    result = await db.execute(
        query.order_by(desc(Notification.created_at))
        .offset((page - 1) * size)
        .limit(size)
    )
    notifications = result.scalars().all()

    return {
        "items": [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "message": n.message,
                "link": n.link,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "total": total,
        "unread_count": unread_count,
        "page": page,
        "size": size,
    }


@router.get("/unread-count")
async def get_unread_count(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """읽지 않은 알림 수"""
    user = await require_current_user(request, db)

    count = (await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
        )
    )).scalar()

    return {"unread_count": count}


@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """알림 읽음 처리"""
    user = await require_current_user(request, db)

    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")

    notif.is_read = True
    await db.commit()

    return {"message": "읽음 처리되었습니다"}


@router.patch("/read-all")
async def mark_all_as_read(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """모든 알림 읽음 처리"""
    user = await require_current_user(request, db)

    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    await db.commit()

    return {"message": "모든 알림을 읽음 처리했습니다"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """알림 삭제"""
    user = await require_current_user(request, db)

    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")

    await db.delete(notif)
    await db.commit()

    return {"message": "알림이 삭제되었습니다"}
