"""능동적 알림 서비스 — 6차 개발 Phase 3-1

10개 트리거를 스케줄러에서 주기적으로 검사하여
조건 충족 시 Notification 레코드를 생성한다.

트리거:
1. 마감 D-1                  2. 마감 당일
3. 마감 초과                  4. 3일간 미업데이트
5. 피드백 도착 (실시간→별도)   6. 출근 미기록 (09:30)
7. 퇴근 시간 (정책 기준)      8. 주간 보고 (금 16:00)
9. 읽지 않은 채팅 (30분)      10. 초대 미수락 (3일)
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    async_session, utc_now,
    Task, Notification, Attendance, AttendancePolicy,
    TeamMember, PendingInvite,
    ChatRoomMember, RoomMessage,
)

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


async def _create_notification(
    db: AsyncSession, user_id: int, ntype: str, title: str,
    message: str, link: str | None = None,
):
    """중복 방지: 동일 type+user+title 24시간 내 1회만 생성"""
    cutoff = utc_now() - timedelta(hours=24)
    existing = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.type == ntype,
            Notification.title == title,
            Notification.created_at > cutoff,
        )
    )
    if existing.scalar_one_or_none():
        return
    db.add(Notification(
        user_id=user_id, type=ntype, title=title,
        message=message, link=link,
    ))


async def check_deadline_notifications(db: AsyncSession):
    """트리거 1~3: 마감 D-1 / 당일 / 초과"""
    now_kst = datetime.now(KST)
    today = now_kst.strftime("%Y-%m-%d")
    tomorrow = (now_kst + timedelta(days=1)).strftime("%Y-%m-%d")

    tasks = await db.execute(
        select(Task).where(
            Task.status.notin_(["completed", "confirmed"]),
            Task.due_date != None,  # noqa: E711
            Task.assignee_id != None,  # noqa: E711
        )
    )
    for task in tasks.scalars().all():
        uid = task.assignee_id
        if task.due_date == tomorrow:
            await _create_notification(
                db, uid, "deadline_d1",
                f"{task.task_name} 업무가 내일 마감입니다",
                f"마감일: {task.due_date}",
                "#/my-tasks",
            )
        elif task.due_date == today:
            await _create_notification(
                db, uid, "deadline_today",
                f"{task.task_name} 업무가 오늘 마감입니다",
                f"마감일: {task.due_date}",
                "#/my-tasks",
            )
        elif task.due_date < today:
            days_late = (now_kst.date() - datetime.strptime(task.due_date, "%Y-%m-%d").date()).days
            await _create_notification(
                db, uid, "deadline_overdue",
                f"{task.task_name} 업무가 {days_late}일 지연되었습니다",
                f"마감일: {task.due_date}",
                "#/my-tasks",
            )


async def check_stale_tasks(db: AsyncSession):
    """트리거 4: 3일간 미업데이트 업무"""
    cutoff = (utc_now() - timedelta(days=3)).isoformat()
    tasks = await db.execute(
        select(Task).where(
            Task.status == "in_progress",
            Task.updated_at < cutoff,
            Task.assignee_id != None,  # noqa: E711
        )
    )
    for task in tasks.scalars().all():
        await _create_notification(
            db, task.assignee_id, "stale_task",
            f"{task.task_name} 업무가 3일간 변동 없습니다",
            "상태를 업데이트해 주세요",
            "#/my-tasks",
        )


async def check_attendance_missing(db: AsyncSession):
    """트리거 6: 출근 미기록 (평일 09:30 이후)"""
    now_kst = datetime.now(KST)
    if now_kst.weekday() >= 5:  # 주말 스킵
        return
    today = now_kst.strftime("%Y-%m-%d")

    # 모든 팀의 활성 멤버 조회
    members = await db.execute(
        select(TeamMember.user_id, TeamMember.team_id)
    )
    for user_id, team_id in members.all():
        att = await db.execute(
            select(Attendance).where(
                Attendance.user_id == user_id,
                Attendance.team_id == team_id,
                Attendance.date == today,
            )
        )
        record = att.scalar_one_or_none()
        if not record or not record.check_in:
            await _create_notification(
                db, user_id, "attendance_missing",
                "오늘 출근 기록이 없어요",
                "업무 시작하기 버튼을 눌러주세요",
                "check-in",
            )


async def check_checkout_time(db: AsyncSession):
    """트리거 7: 퇴근 시간 도래"""
    now_kst = datetime.now(KST)
    if now_kst.weekday() >= 5:
        return
    today = now_kst.strftime("%Y-%m-%d")
    now_time = now_kst.strftime("%H:%M")

    # 각 팀 정책의 퇴근 시간 확인
    policies = await db.execute(select(AttendancePolicy))
    now_h, now_m = map(int, now_time.split(":"))
    now_total_min = now_h * 60 + now_m

    for policy in policies.scalars().all():
        check_out = policy.default_check_out or "18:00"
        co_h, co_m = map(int, check_out.split(":"))
        co_total_min = co_h * 60 + co_m
        diff_minutes = abs(now_total_min - co_total_min)
        if diff_minutes > 15:
            continue

        # 오늘 출근한 사용자 중 아직 퇴근 안 한 사람
        att_result = await db.execute(
            select(Attendance).where(
                Attendance.team_id == policy.team_id,
                Attendance.date == today,
                Attendance.check_in != None,  # noqa: E711
                Attendance.check_out == None,  # noqa: E711
            )
        )
        for att in att_result.scalars().all():
            await _create_notification(
                db, att.user_id, "checkout_reminder",
                "오늘의 업무를 정리할까요?",
                "업무 보고를 작성하고 퇴근하세요",
                "work-report",
            )


async def check_weekly_report_reminder(db: AsyncSession):
    """트리거 8: 주간 보고 (금 16:00)"""
    now_kst = datetime.now(KST)
    if now_kst.weekday() != 4:  # 금요일만
        return

    members = await db.execute(
        select(TeamMember.user_id).distinct()
    )
    for (user_id,) in members.all():
        await _create_notification(
            db, user_id, "weekly_report_reminder",
            "이번 주 주간 보고서를 작성할까요?",
            "한 주간의 업무를 정리해 보세요",
            "#/reports",
        )


async def check_unread_chat(db: AsyncSession):
    """트리거 9: 읽지 않은 채팅 (30분 이상)"""
    cutoff = utc_now() - timedelta(minutes=30)

    memberships = await db.execute(select(ChatRoomMember))
    user_unread = {}

    for m in memberships.scalars().all():
        last_read = m.last_read_at
        if last_read:
            count_result = await db.execute(
                select(func.count(RoomMessage.id)).where(
                    RoomMessage.room_id == m.room_id,
                    RoomMessage.sender_id != m.user_id,
                    RoomMessage.created_at > last_read,
                    RoomMessage.created_at < cutoff,
                )
            )
        else:
            count_result = await db.execute(
                select(func.count(RoomMessage.id)).where(
                    RoomMessage.room_id == m.room_id,
                    RoomMessage.sender_id != m.user_id,
                    RoomMessage.created_at < cutoff,
                )
            )
        cnt = count_result.scalar() or 0
        if cnt > 0:
            user_unread[m.user_id] = user_unread.get(m.user_id, 0) + cnt

    for user_id, total in user_unread.items():
        await _create_notification(
            db, user_id, "unread_chat",
            f"읽지 않은 채팅 {total}건이 있습니다",
            "30분 이상 확인하지 않은 메시지가 있어요",
            "#/chat",
        )


async def check_pending_invites(db: AsyncSession):
    """트리거 10: 초대 미수락 (3일)"""
    cutoff = utc_now() - timedelta(days=3)
    invites = await db.execute(
        select(PendingInvite).where(
            PendingInvite.status == "pending",
            PendingInvite.created_at < cutoff,
        )
    )
    for invite in invites.scalars().all():
        # 초대를 보낸 팀 owner에게 알림
        owner_result = await db.execute(
            select(TeamMember.user_id).where(
                TeamMember.team_id == invite.team_id,
                TeamMember.role == "owner",
            )
        )
        for (owner_id,) in owner_result.all():
            await _create_notification(
                db, owner_id, "invite_pending",
                "팀 초대가 3일간 대기 중입니다",
                f"{invite.email}님의 초대가 아직 수락되지 않았습니다",
                "#/settings",
            )


# ── 통합 실행 (스케줄러에서 호출) ──

async def run_proactive_notifications():
    """모든 능동적 알림 트리거 실행"""
    async with async_session() as db:
        try:
            now_kst = datetime.now(KST)
            hour = now_kst.hour

            # 매일 09:00 트리거 (1~3번)
            if hour == 9:
                await check_deadline_notifications(db)

            # 09:30 출근 미기록 (6번)
            if hour == 9 and now_kst.minute >= 30:
                await check_attendance_missing(db)

            # 10:00 미업데이트 + 초대 미수락 (4, 10번)
            if hour == 10:
                await check_stale_tasks(db)
                await check_pending_invites(db)

            # 퇴근 시간 (7번) — 매 실행 시 확인
            await check_checkout_time(db)

            # 금 16:00 주간 보고 (8번)
            if now_kst.weekday() == 4 and hour == 16:
                await check_weekly_report_reminder(db)

            # 30분마다 읽지 않은 채팅 (9번)
            await check_unread_chat(db)

            await db.commit()
            logger.debug("능동적 알림 체크 완료")

        except Exception as e:
            logger.error(f"능동적 알림 처리 실패: {e}")
            await db.rollback()
