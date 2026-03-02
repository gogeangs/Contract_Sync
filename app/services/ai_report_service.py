"""AI 보고서 서비스 — Phase 3"""
import asyncio
import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    AIReport, Task, Project, Client, ClientFeedback, User,
    utc_now,
)
from app.services.common import (
    get_user_team_ids, access_filter, check_team_permission, log_activity, get_accessible,
)

logger = logging.getLogger(__name__)

_REPORT_TYPE_LABELS = {
    "periodic": "정기 보고서",
    "completion": "프로젝트 완료 보고서",
}


# ── 컨텍스트 수집 헬퍼 ──

async def _gather_periodic_context(
    db: AsyncSession, project: Project, period_start: str, period_end: str,
) -> dict:
    """정기 보고에 필요한 데이터 수집"""
    client = await db.get(Client, project.client_id) if project.client_id else None

    # 기간 내 완료 업무
    completed_q = await db.execute(
        select(Task).where(
            Task.project_id == project.id,
            Task.status.in_(["completed", "report_sent", "confirmed"]),
            Task.completed_at != None,  # noqa: E711
            Task.completed_at >= datetime.fromisoformat(period_start),
            Task.completed_at <= datetime.fromisoformat(period_end + "T23:59:59"),
        )
    )
    completed_tasks = completed_q.scalars().all()

    # 진행 중 업무
    ip_q = await db.execute(
        select(Task).where(
            Task.project_id == project.id,
            Task.status == "in_progress",
        )
    )
    in_progress_tasks = ip_q.scalars().all()

    # 예정 업무 (대기 중, 마감일이 기간 이후)
    upcoming_q = await db.execute(
        select(Task).where(
            Task.project_id == project.id,
            Task.status == "pending",
        ).order_by(Task.due_date).limit(10)
    )
    upcoming_tasks = upcoming_q.scalars().all()

    # 피드백 통계
    fb_q = await db.execute(
        select(
            ClientFeedback.feedback_type,
            func.count(ClientFeedback.id),
        ).join(Task, ClientFeedback.task_id == Task.id).where(
            Task.project_id == project.id,
        ).group_by(ClientFeedback.feedback_type)
    )
    fb_rows = fb_q.all()
    feedback_summary = {"confirmed": 0, "revision_requested": 0, "pending": 0}
    for ftype, cnt in fb_rows:
        if ftype == "confirmed":
            feedback_summary["confirmed"] = cnt
        elif ftype == "revision":
            feedback_summary["revision_requested"] = cnt
        else:
            feedback_summary["pending"] += cnt

    # 전체 진행률
    total_q = await db.execute(
        select(func.count(Task.id)).where(Task.project_id == project.id)
    )
    total_tasks = total_q.scalar() or 0

    completed_count_q = await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project.id,
            Task.status.in_(["completed", "report_sent", "confirmed"]),
        )
    )
    completed_count = completed_count_q.scalar() or 0
    progress_pct = round(completed_count / total_tasks * 100) if total_tasks else 0

    # 지연 업무 → 이슈
    issues = []
    for t in in_progress_tasks:
        if t.due_date and t.due_date < period_end:
            issues.append(f"'{t.task_name}' 마감일({t.due_date}) 초과")

    def _task_dict(t: Task) -> dict:
        assignee_name = ""
        return {
            "task_name": t.task_name,
            "phase": t.phase or "",
            "completed_date": t.completed_at.strftime("%Y-%m-%d") if t.completed_at else "",
            "due_date": t.due_date or "",
            "assignee": assignee_name,
            "status": t.status,
        }

    return {
        "project_name": project.project_name,
        "client_name": client.name if client else "",
        "period_start": period_start,
        "period_end": period_end,
        "completed_tasks": [_task_dict(t) for t in completed_tasks],
        "in_progress_tasks": [_task_dict(t) for t in in_progress_tasks],
        "upcoming_tasks": [_task_dict(t) for t in upcoming_tasks],
        "feedback_summary": feedback_summary,
        "issues": issues,
        "overall_progress": {
            "total_tasks": total_tasks,
            "completed_tasks": completed_count,
            "progress_percent": progress_pct,
        },
    }


async def _gather_completion_context(
    db: AsyncSession, project: Project,
) -> dict:
    """프로젝트 완료 보고에 필요한 데이터 수집"""
    client = await db.get(Client, project.client_id) if project.client_id else None

    # 전체 업무
    all_q = await db.execute(
        select(Task).where(Task.project_id == project.id).order_by(Task.sort_order)
    )
    all_tasks = all_q.scalars().all()

    # 단계 목록
    phases = list(dict.fromkeys(t.phase for t in all_tasks if t.phase))

    # 일정 준수율
    on_time = 0
    total_with_due = 0
    for t in all_tasks:
        if t.completed_at and t.due_date:
            total_with_due += 1
            completed_str = t.completed_at.strftime("%Y-%m-%d")
            if completed_str <= t.due_date:
                on_time += 1

    on_time_rate = round(on_time / total_with_due * 100) if total_with_due else 100

    # 기간 계산
    planned_days = project.total_duration_days or 0
    actual_days = 0
    if project.start_date and project.end_date:
        try:
            s = datetime.fromisoformat(project.start_date)
            e = datetime.fromisoformat(project.end_date)
            actual_days = (e - s).days
        except (ValueError, TypeError):
            pass

    # 피드백 이력
    fb_q = await db.execute(
        select(
            ClientFeedback.feedback_type,
            func.count(ClientFeedback.id),
        ).join(Task, ClientFeedback.task_id == Task.id).where(
            Task.project_id == project.id,
        ).group_by(ClientFeedback.feedback_type)
    )
    fb_rows = fb_q.all()
    fb_total = sum(cnt for _, cnt in fb_rows)
    fb_confirmed = sum(cnt for ft, cnt in fb_rows if ft == "confirmed")
    fb_revision = sum(cnt for ft, cnt in fb_rows if ft == "revision")

    def _task_dict(t: Task) -> dict:
        is_on_time = True
        if t.completed_at and t.due_date:
            is_on_time = t.completed_at.strftime("%Y-%m-%d") <= t.due_date
        return {
            "task_name": t.task_name,
            "phase": t.phase or "",
            "status": t.status,
            "completed_date": t.completed_at.strftime("%Y-%m-%d") if t.completed_at else "",
            "due_date": t.due_date or "",
            "is_on_time": is_on_time,
        }

    return {
        "project_name": project.project_name,
        "client_name": client.name if client else "",
        "start_date": project.start_date or "",
        "end_date": project.end_date or "",
        "all_tasks": [_task_dict(t) for t in all_tasks],
        "phases": phases,
        "feedback_history": {
            "total": fb_total,
            "confirmed": fb_confirmed,
            "revision_requested": fb_revision,
            "avg_response_days": 0,
        },
        "schedule_adherence": {
            "planned_days": planned_days,
            "actual_days": actual_days,
            "on_time_rate": on_time_rate,
        },
    }


# ── enrich ──

async def enrich_report(db: AsyncSession, report: AIReport) -> dict:
    """응답용 dict 변환 (project_name 조인)"""
    project = await db.get(Project, report.project_id)
    return {
        "id": report.id,
        "project_id": report.project_id,
        "report_type": report.report_type,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "title": report.title,
        "content_html": report.content_html,
        "content_json": report.content_json,
        "status": report.status,
        "sent_to": report.sent_to,
        "sent_at": report.sent_at,
        "created_at": report.created_at,
        "project_name": project.project_name if project else None,
    }


# ── AI 보고서 CRUD ──

async def generate_report(
    db: AsyncSession, user: User, project_id: int, data,
) -> AIReport:
    """AI 보고서 생성 → draft"""
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    await check_team_permission(db, project.team_id, user.id, "report.create")

    from app.services.gemini_service import GeminiService

    try:
        gemini = GeminiService()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if data.report_type == "periodic":
        if not data.period_start or not data.period_end:
            raise HTTPException(status_code=400, detail="정기 보고는 기간을 지정해야 합니다")
        context = await _gather_periodic_context(db, project, data.period_start, data.period_end)
        try:
            result = await gemini.generate_periodic_report(context)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))
    elif data.report_type == "completion":
        context = await _gather_completion_context(db, project)
        try:
            result = await gemini.generate_completion_summary(context)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=400, detail="유효하지 않은 보고서 유형입니다")

    report = AIReport(
        project_id=project_id,
        report_type=data.report_type,
        period_start=data.period_start,
        period_end=data.period_end,
        title=result["title"],
        content_html=result["content_html"],
        content_json=result.get("content_json"),
        status="draft",
    )
    db.add(report)
    await db.flush()

    await log_activity(
        db, user.id, "create", "ai_report", result["title"],
        project_id=project_id, team_id=project.team_id,
    )
    await db.commit()
    await db.refresh(report)
    return report


async def list_project_reports(
    db: AsyncSession, user: User, project_id: int,
) -> tuple[list[AIReport], int]:
    """프로젝트별 보고서 목록"""
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    result = await db.execute(
        select(AIReport).where(AIReport.project_id == project_id)
        .order_by(desc(AIReport.created_at))
    )
    reports = result.scalars().all()

    return reports, len(reports)


async def list_all_reports(
    db: AsyncSession, user: User, page: int = 1, size: int = 20,
) -> tuple[list[AIReport], int]:
    """전체 보고서 목록 (접근 가능한 프로젝트만)"""
    team_ids = await get_user_team_ids(db, user.id)

    # 총 개수
    count_q = await db.execute(
        select(func.count(AIReport.id)).join(Project, AIReport.project_id == Project.id)
        .where(access_filter(Project, user.id, team_ids))
    )
    total = count_q.scalar() or 0

    # 페이지네이션
    offset = (page - 1) * size
    result = await db.execute(
        select(AIReport).join(Project, AIReport.project_id == Project.id)
        .where(access_filter(Project, user.id, team_ids))
        .order_by(desc(AIReport.created_at))
        .offset(offset).limit(size)
    )
    reports = result.scalars().all()

    return reports, total


async def get_report(
    db: AsyncSession, user: User, report_id: int,
) -> AIReport:
    """보고서 상세 조회"""
    report = await db.get(AIReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다")

    # 프로젝트 접근 확인
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, report.project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다")

    return report


async def update_report(
    db: AsyncSession, user: User, report_id: int, data,
) -> AIReport:
    """보고서 편집 (draft만)"""
    report = await get_report(db, user, report_id)

    if report.status != "draft":
        raise HTTPException(status_code=400, detail="초안 상태의 보고서만 편집할 수 있습니다")

    project = await db.get(Project, report.project_id)
    await check_team_permission(db, project.team_id, user.id, "report.create")

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(report, field, value)

    await log_activity(
        db, user.id, "update", "ai_report", report.title,
        project_id=report.project_id, team_id=project.team_id,
    )
    await db.commit()
    await db.refresh(report)
    return report


async def delete_report(
    db: AsyncSession, user: User, report_id: int,
) -> None:
    """보고서 삭제 (draft만)"""
    report = await get_report(db, user, report_id)

    if report.status != "draft":
        raise HTTPException(status_code=400, detail="초안 상태의 보고서만 삭제할 수 있습니다")

    project = await db.get(Project, report.project_id)
    await check_team_permission(db, project.team_id, user.id, "report.create")

    await log_activity(
        db, user.id, "delete", "ai_report", report.title,
        project_id=report.project_id, team_id=project.team_id,
    )
    await db.delete(report)
    await db.commit()


async def _send_report_email_background(report_id: int, recipient_emails: list[str]):
    """백그라운드 이메일 발송 (API 응답 블로킹 방지)"""
    from app.database import async_session
    from app.services.email_service import _render_template, send_email_with_retry

    try:
        async with async_session() as db:
            report = await db.get(AIReport, report_id)
            if not report or report.status != "sent":
                return

            project = await db.get(Project, report.project_id)
            if not project:
                return

            report_type_label = _REPORT_TYPE_LABELS.get(report.report_type, "보고서")
            period = ""
            if report.period_start and report.period_end:
                period = f"{report.period_start} ~ {report.period_end}"

            html_body = _render_template("periodic_report.html", {
                "project_name": project.project_name,
                "report_type_label": report_type_label,
                "period": period,
                "report_html": report.content_html,
            })

            subject = f"[{project.project_name}] {report.title}"

            success = await send_email_with_retry(
                to_emails=recipient_emails,
                subject=subject,
                html_body=html_body,
            )

            if not success:
                report.status = "failed"
                await db.commit()
                logger.error(f"AI 보고서 이메일 발송 실패: report_id={report_id}")
    except Exception as e:
        logger.error(f"AI 보고서 이메일 백그라운드 발송 오류: {e}")


async def send_report(
    db: AsyncSession, user: User, report_id: int, data,
) -> AIReport:
    """보고서 이메일 발송 (draft → sent)"""
    report = await get_report(db, user, report_id)

    if report.status != "draft":
        raise HTTPException(status_code=400, detail="초안 상태의 보고서만 발송할 수 있습니다")

    project = await db.get(Project, report.project_id)
    await check_team_permission(db, project.team_id, user.id, "report.send")

    report.status = "sent"
    report.sent_to = data.recipient_emails
    report.sent_at = utc_now()

    await log_activity(
        db, user.id, "send", "ai_report", report.title,
        project_id=report.project_id, team_id=project.team_id,
        detail=f"수신: {', '.join(data.recipient_emails)}",
    )
    await db.commit()
    await db.refresh(report)

    # 백그라운드 이메일 발송 (API 응답 블로킹 방지)
    asyncio.create_task(_send_report_email_background(report.id, data.recipient_emails))

    return report
