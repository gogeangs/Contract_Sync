"""AI 업무 보고 서비스 — 6차 개발 Phase 3-3

퇴근 시 AI가 오늘의 활동을 자동 요약.
데이터 소스: tasks(상태 변경), board_posts(게시글), room_messages(채팅), feedback_responses(피드백)
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    ActivityLog, User, BoardPost, RoomMessage,
)

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


async def generate_daily_work_summary(db: AsyncSession, user_id: int) -> dict:
    """오늘의 활동 데이터 수집 → 요약 반환"""
    now_kst = datetime.now(KST)
    today_start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    # UTC로 변환 (DB는 naive UTC 저장)
    today_start_utc = (today_start - timedelta(hours=9)).replace(tzinfo=None)

    activities = []

    # 1. 오늘 상태 변경된 업무
    task_logs = await db.execute(
        select(ActivityLog).where(
            ActivityLog.user_id == user_id,
            ActivityLog.target_type == "task",
            ActivityLog.created_at >= today_start_utc,
        ).order_by(ActivityLog.created_at.desc()).limit(20)
    )
    for log in task_logs.scalars().all():
        icon = "✅" if "완료" in (log.detail or "") or "completed" in (log.detail or "") else "🔄"
        activities.append({
            "type": "task",
            "icon": icon,
            "description": f"{log.target_name or '업무'} — {log.action}",
            "detail": log.detail,
        })

    # 2. 오늘 작성한 게시글
    posts = await db.execute(
        select(BoardPost).where(
            BoardPost.author_id == user_id,
            BoardPost.created_at >= today_start_utc,
        )
    )
    for post in posts.scalars().all():
        activities.append({
            "type": "post",
            "icon": "📝",
            "description": f"게시글 작성: {post.title}",
        })

    # 3. 오늘 발송한 채팅 수
    chat_count = await db.execute(
        select(func.count(RoomMessage.id)).where(
            RoomMessage.sender_id == user_id,
            RoomMessage.created_at >= today_start_utc,
        )
    )
    msg_count = chat_count.scalar() or 0
    if msg_count > 0:
        activities.append({
            "type": "chat",
            "icon": "💬",
            "description": f"채팅 메시지 {msg_count}건 발송",
        })

    # 4. 오늘 처리한 피드백 (알림 기반)
    from app.database import Notification
    fb_notifs = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.type.in_(["feedback_received", "revision_requested"]),
            Notification.created_at >= today_start_utc,
        )
    )
    fb_count = fb_notifs.scalar() or 0
    if fb_count > 0:
        activities.append({
            "type": "feedback",
            "icon": "📋",
            "description": f"피드백 처리 {fb_count}건",
        })

    user = await db.get(User, user_id)

    return {
        "user_name": user.name if user else "사용자",
        "date": now_kst.strftime("%Y-%m-%d"),
        "activities": activities,
        "summary": f"오늘 총 {len(activities)}건의 활동이 있었습니다." if activities else "오늘은 기록된 활동이 없습니다.",
    }
