"""주간 요약 리포트 — 2차 개발 #10

매주 월요일 09:00 KST에 실행하여 팀/개인별 주간 리포트를 생성한다.
scheduler_service.py의 scheduler_loop에서 호출.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func

from app.database import (
    Task, Team, TeamMember, Notification, User,
    async_session, utc_now,
)

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


async def generate_weekly_reports():
    """팀별 + 개인 주간 요약 생성 (1회 실행)"""
    now_kst = datetime.now(KST)
    # 이번 주 월요일 00:00 KST → 지난 7일간 데이터
    week_start = (now_kst - timedelta(days=7)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    # naive UTC로 변환 (DB 비교용)
    week_start_utc = week_start.astimezone(timezone.utc).replace(tzinfo=None)
    now_utc = utc_now()
    today_str = now_kst.strftime("%Y-%m-%d")

    generated = 0

    async with async_session() as db:
        try:
            # 모든 팀 조회
            teams = (await db.execute(select(Team))).scalars().all()

            for team in teams:
                report = await _build_team_report(db, team.id, week_start_utc, now_utc, today_str)
                if not report:
                    continue

                # 팀 멤버에게 알림
                members = (await db.execute(
                    select(TeamMember.user_id).where(TeamMember.team_id == team.id)
                )).scalars().all()

                for uid in members:
                    db.add(Notification(
                        user_id=uid,
                        type="weekly_report",
                        title=f"[{team.name}] 주간 요약 리포트가 생성되었습니다",
                        message=report["summary"],
                        link=json.dumps({"team_id": team.id, "week": today_str}),
                    ))

                generated += 1

            if generated > 0:
                await db.commit()
                logger.info(f"주간 리포트 생성: {generated}개 팀")
            else:
                logger.debug("주간 리포트: 생성 대상 없음")

        except Exception as e:
            logger.error(f"주간 리포트 생성 실패: {e}")
            await db.rollback()

    return generated


async def get_weekly_report_data(db, team_id: int | None, user_id: int, week_offset: int = 0) -> dict:
    """주간 리포트 데이터 조회 (API 호출용)"""
    now_kst = datetime.now(KST)
    # week_offset: 0=이번 주, -1=지난 주, ...
    target_monday = now_kst - timedelta(days=now_kst.weekday()) + timedelta(weeks=week_offset)
    week_start = target_monday.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)

    week_start_utc = week_start.astimezone(timezone.utc).replace(tzinfo=None)
    week_end_utc = week_end.astimezone(timezone.utc).replace(tzinfo=None)
    today_str = now_kst.strftime("%Y-%m-%d")

    if team_id:
        return await _build_team_report(db, team_id, week_start_utc, week_end_utc, today_str)
    else:
        return await _build_personal_report(db, user_id, week_start_utc, week_end_utc, today_str)


async def _build_team_report(db, team_id: int, week_start, week_end, today_str: str) -> dict | None:
    """팀 기준 주간 리포트 데이터"""
    base_filter = Task.team_id == team_id

    return await _aggregate_report(db, base_filter, week_start, week_end, today_str)


async def _build_personal_report(db, user_id: int, week_start, week_end, today_str: str) -> dict | None:
    """개인 기준 주간 리포트 데이터"""
    from sqlalchemy import or_
    base_filter = or_(Task.user_id == user_id, Task.assignee_id == user_id)

    return await _aggregate_report(db, base_filter, week_start, week_end, today_str)


async def _aggregate_report(db, base_filter, week_start, week_end, today_str: str) -> dict | None:
    """공통 집계 로직"""
    # 1. 이번 주 완료 업무
    completed_result = await db.execute(
        select(Task).where(
            base_filter,
            Task.status == "completed",
            Task.completed_at >= week_start,
            Task.completed_at < week_end,
        ).order_by(Task.completed_at)
    )
    completed_tasks = completed_result.scalars().all()

    # 2. 진행 중 업무
    in_progress_result = await db.execute(
        select(Task).where(base_filter, Task.status == "in_progress")
    )
    in_progress_tasks = in_progress_result.scalars().all()

    # 3. 지연 업무 (마감일 < 오늘 & 미완료)
    overdue_result = await db.execute(
        select(Task).where(
            base_filter,
            Task.due_date < today_str,
            Task.status.notin_(["completed", "confirmed"]),
            Task.due_date != None,  # noqa: E711
        )
    )
    overdue_tasks = overdue_result.scalars().all()

    # 4. 신규 생성 업무
    new_result = await db.execute(
        select(Task).where(
            base_filter,
            Task.created_at >= week_start,
            Task.created_at < week_end,
        )
    )
    new_tasks = new_result.scalars().all()

    # 5. 전체 업무 수
    total = (await db.execute(
        select(func.count()).select_from(Task).where(base_filter)
    )).scalar() or 0

    # 담당자 이름 조회
    assignee_ids = set()
    for t in completed_tasks + in_progress_tasks + overdue_tasks + new_tasks:
        if t.assignee_id:
            assignee_ids.add(t.assignee_id)
        assignee_ids.add(t.user_id)

    name_map = {}
    if assignee_ids:
        users = (await db.execute(
            select(User.id, User.name, User.email).where(User.id.in_(list(assignee_ids)))
        )).all()
        name_map = {u.id: u.name or u.email for u in users}

    def _task_info(t):
        return {
            "id": t.id,
            "task_name": t.task_name,
            "assignee_name": name_map.get(t.assignee_id, "미지정"),
            "due_date": t.due_date,
            "status": t.status,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }

    completed_count = len(completed_tasks)
    in_progress_count = len(in_progress_tasks)
    overdue_count = len(overdue_tasks)
    new_count = len(new_tasks)
    completion_rate = round(completed_count / total * 100) if total > 0 else 0

    summary = f"완료 {completed_count}건 | 진행중 {in_progress_count}건 | 지연 {overdue_count}건 | 신규 {new_count}건"

    return {
        "summary": summary,
        "completion_rate": completion_rate,
        "total_tasks": total,
        "completed": [_task_info(t) for t in completed_tasks],
        "in_progress": [_task_info(t) for t in in_progress_tasks],
        "overdue": [_task_info(t) for t in overdue_tasks],
        "new_tasks": [_task_info(t) for t in new_tasks],
        "stats": {
            "completed_count": completed_count,
            "in_progress_count": in_progress_count,
            "overdue_count": overdue_count,
            "new_count": new_count,
        },
    }
