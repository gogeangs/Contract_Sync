"""반복 업무 스케줄러 — Phase 5 부속 (§15)

매일 00:00 KST (15:00 UTC)에 실행하여 활성 반복 업무 설정에 따라
Task를 자동 생성한다. main.py lifespan에서 asyncio.create_task로 등록.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import RecurringTask, Task, Project, async_session, utc_now

logger = logging.getLogger(__name__)

# KST = UTC+9
KST = timezone(timedelta(hours=9))


def _should_generate(rt: RecurringTask, now_kst: datetime) -> bool:
    """오늘 이 반복 업무를 생성해야 하는지 판단"""
    if not rt.is_active:
        return False

    weekday = now_kst.weekday()  # 0=월 ~ 6=일
    day = now_kst.day

    if rt.frequency == "daily":
        return True
    elif rt.frequency == "weekly":
        return rt.day_of_week == weekday
    elif rt.frequency == "monthly":
        return rt.day_of_month == day
    return False


def _already_generated_today(rt: RecurringTask, now_kst: datetime) -> bool:
    """오늘 이미 생성했는지 확인 (중복 방지)"""
    if not rt.last_generated_at:
        return False
    last_kst = rt.last_generated_at.replace(tzinfo=timezone.utc).astimezone(KST)
    return last_kst.date() == now_kst.date()


async def generate_recurring_tasks():
    """활성 반복 업무 → Task 자동 생성 (1회 실행)"""
    now_kst = datetime.now(KST)
    generated = 0

    async with async_session() as db:
        try:
            result = await db.execute(
                select(RecurringTask).where(RecurringTask.is_active == True)  # noqa: E712
            )
            recurring_tasks = result.scalars().all()

            for rt in recurring_tasks:
                if not _should_generate(rt, now_kst):
                    continue
                if _already_generated_today(rt, now_kst):
                    continue

                # 프로젝트 상태 확인 (활성 프로젝트만)
                project = await db.get(Project, rt.project_id)
                if not project or project.status not in ("active", "planning"):
                    continue

                # Task 생성
                task = Task(
                    project_id=rt.project_id,
                    user_id=project.user_id,
                    team_id=project.team_id,
                    task_name=rt.task_name,
                    description=rt.description,
                    priority=rt.priority,
                    assignee_id=rt.assignee_id,
                    status="pending",
                    due_date=now_kst.strftime("%Y-%m-%d"),
                )
                db.add(task)
                await db.flush()
                task.task_code = f"TASK-{task.id:03d}"

                # 마지막 생성 시각 갱신
                rt.last_generated_at = utc_now()
                generated += 1

            if generated > 0:
                await db.commit()
                logger.info(f"반복 업무 자동 생성: {generated}건")
            else:
                logger.debug("반복 업무 자동 생성: 해당 없음")

        except Exception as e:
            logger.error(f"반복 업무 자동 생성 실패: {e}")
            await db.rollback()

    return generated


async def scheduler_loop():
    """매일 KST 00:00에 반복 업무를 생성하는 무한 루프"""
    while True:
        now_kst = datetime.now(KST)
        # 다음 00:00 KST까지 대기
        tomorrow = (now_kst + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        wait_seconds = (tomorrow - now_kst).total_seconds()
        logger.info(f"스케줄러: 다음 실행까지 {wait_seconds:.0f}초 대기 (KST {tomorrow.strftime('%Y-%m-%d %H:%M')})")

        await asyncio.sleep(wait_seconds)

        try:
            await generate_recurring_tasks()
        except Exception as e:
            logger.error(f"스케줄러 실행 오류: {e}")


async def weekly_report_loop():
    """매주 월요일 09:00 KST에 주간 리포트 생성 (#10)"""
    from app.services.weekly_report import generate_weekly_reports

    while True:
        now_kst = datetime.now(KST)

        # 다음 월요일 09:00 KST 계산
        days_until_monday = (7 - now_kst.weekday()) % 7
        if days_until_monday == 0 and now_kst.hour >= 9:
            days_until_monday = 7
        next_monday_9am = (now_kst + timedelta(days=days_until_monday)).replace(
            hour=9, minute=0, second=0, microsecond=0,
        )
        wait_seconds = (next_monday_9am - now_kst).total_seconds()
        logger.info(f"주간 리포트 스케줄러: 다음 실행까지 {wait_seconds:.0f}초 대기 (KST {next_monday_9am.strftime('%Y-%m-%d %H:%M')})")

        await asyncio.sleep(wait_seconds)

        try:
            await generate_weekly_reports()
        except Exception as e:
            logger.error(f"주간 리포트 생성 오류: {e}")


async def figma_check_loop():
    """Figma 변경 감지 — 1시간 간격 (3차 개발 S3-5)"""
    from app.services.figma_service import check_figma_updates

    while True:
        await asyncio.sleep(3600)  # 1시간
        try:
            await check_figma_updates()
        except Exception as e:
            logger.error(f"Figma 변경 감지 오류: {e}")


async def feedback_reminder_loop():
    """피드백 리마인더 — 매일 10:00 KST (3차 개발 S4-5)"""
    from app.services.feedback_request_service import process_feedback_reminders

    while True:
        now_kst = datetime.now(KST)
        # 다음 10:00 KST 계산
        next_10am = now_kst.replace(hour=10, minute=0, second=0, microsecond=0)
        if now_kst.hour >= 10:
            next_10am += timedelta(days=1)
        wait_seconds = (next_10am - now_kst).total_seconds()
        logger.info(f"피드백 리마인더 스케줄러: 다음 실행까지 {wait_seconds:.0f}초 대기 (KST {next_10am.strftime('%Y-%m-%d %H:%M')})")

        await asyncio.sleep(wait_seconds)

        try:
            await process_feedback_reminders()
        except Exception as e:
            logger.error(f"피드백 리마인더 오류: {e}")


async def proactive_notification_loop():
    """능동적 알림 — 30분 간격 (6차 개발 Phase 3-1)"""
    from app.services.proactive_notification_service import run_proactive_notifications

    while True:
        await asyncio.sleep(1800)  # 30분
        try:
            await run_proactive_notifications()
        except Exception as e:
            logger.error(f"능동적 알림 처리 오류: {e}")
