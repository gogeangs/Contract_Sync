"""템플릿 + 반복 업무 서비스 — Phase 5"""
import logging

from fastapi import HTTPException
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import ProjectTemplate, RecurringTask, Project, User
from app.services.common import (
    get_user_team_ids, access_filter, check_team_permission, log_activity, get_accessible,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════
# 템플릿 CRUD
# ══════════════════════════════════════════

async def enrich_template(db: AsyncSession, template: ProjectTemplate) -> dict:
    """응답용 dict 변환"""
    return {
        "id": template.id,
        "user_id": template.user_id,
        "team_id": template.team_id,
        "name": template.name,
        "project_type": template.project_type,
        "description": template.description,
        "task_templates": template.task_templates,
        "schedule_templates": template.schedule_templates,
        "created_at": template.created_at,
    }


async def create_template(db: AsyncSession, user, data, team_id: int | None = None) -> ProjectTemplate:
    """템플릿 저장"""
    team_ids = await get_user_team_ids(db, user.id)

    if team_id:
        if team_id not in team_ids:
            raise HTTPException(status_code=403, detail="해당 팀의 멤버가 아닙니다.")
        await check_team_permission(db, team_id, user.id, "template.create")

    template = ProjectTemplate(
        user_id=user.id,
        team_id=team_id,
        name=data.name,
        project_type=data.project_type,
        description=data.description,
        task_templates=[t.model_dump() for t in data.task_templates] if data.task_templates else None,
        schedule_templates=[s.model_dump() for s in data.schedule_templates] if data.schedule_templates else None,
    )
    db.add(template)
    await db.flush()

    await log_activity(
        db, user.id, "create", "template", data.name,
        team_id=team_id,
        detail=f"{data.project_type} / 업무 {len(data.task_templates or [])}건",
    )
    await db.commit()
    await db.refresh(template)
    return template


async def list_templates(db: AsyncSession, user) -> tuple[list[ProjectTemplate], int]:
    """템플릿 목록 (접근 가능한 것만)"""
    team_ids = await get_user_team_ids(db, user.id)
    af = access_filter(ProjectTemplate, user.id, team_ids)

    count_q = await db.execute(select(func.count(ProjectTemplate.id)).where(af))
    total = count_q.scalar() or 0

    result = await db.execute(
        select(ProjectTemplate).where(af).order_by(desc(ProjectTemplate.created_at))
    )
    templates = result.scalars().all()
    return templates, total


async def get_template(db: AsyncSession, user, template_id: int) -> ProjectTemplate:
    """템플릿 상세 (접근 권한 확인)"""
    team_ids = await get_user_team_ids(db, user.id)
    template = await get_accessible(db, ProjectTemplate, template_id, user.id, team_ids)
    if not template:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다")
    return template


async def update_template(
    db: AsyncSession, user, template_id: int, data,
) -> ProjectTemplate:
    """템플릿 수정"""
    template = await get_template(db, user, template_id)
    if template.team_id:
        await check_team_permission(db, template.team_id, user.id, "template.create")

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(template, key, value)

    await log_activity(
        db, user.id, "update", "template", template.name,
        team_id=template.team_id,
    )
    await db.commit()
    await db.refresh(template)
    return template


async def delete_template(db: AsyncSession, user, template_id: int) -> None:
    """템플릿 삭제"""
    template = await get_template(db, user, template_id)
    if template.team_id:
        await check_team_permission(db, template.team_id, user.id, "template.delete")

    name = template.name
    team_id = template.team_id
    await db.delete(template)

    await log_activity(
        db, user.id, "delete", "template", name,
        team_id=team_id,
    )
    await db.commit()


# ══════════════════════════════════════════
# 반복 업무 CRUD
# ══════════════════════════════════════════

def _validate_frequency(data) -> None:
    """주기 + 요일/일자 필드 정합성 검증"""
    freq = getattr(data, "frequency", None)
    if freq is None:
        return  # Update에서 frequency를 변경하지 않는 경우
    if freq == "weekly" and getattr(data, "day_of_week", None) is None:
        raise HTTPException(
            status_code=422, detail="주간 반복에는 day_of_week(0=월~6=일)가 필요합니다"
        )
    if freq == "monthly" and getattr(data, "day_of_month", None) is None:
        raise HTTPException(
            status_code=422, detail="월간 반복에는 day_of_month(1~31)가 필요합니다"
        )


async def enrich_recurring_task(db: AsyncSession, task: RecurringTask) -> dict:
    """응답용 dict 변환 (assignee_name 조인)"""
    assignee_name = None
    if task.assignee_id:
        assignee = await db.get(User, task.assignee_id)
        assignee_name = assignee.name if assignee else None

    return {
        "id": task.id,
        "project_id": task.project_id,
        "task_name": task.task_name,
        "description": task.description,
        "frequency": task.frequency,
        "day_of_month": task.day_of_month,
        "day_of_week": task.day_of_week,
        "priority": task.priority,
        "assignee_id": task.assignee_id,
        "is_active": task.is_active,
        "last_generated_at": task.last_generated_at,
        "created_at": task.created_at,
        "assignee_name": assignee_name,
    }


async def create_recurring_task(
    db: AsyncSession, user, project_id: int, data,
) -> RecurringTask:
    """반복 업무 설정"""
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    await check_team_permission(db, project.team_id, user.id, "task.create")
    _validate_frequency(data)

    task = RecurringTask(
        project_id=project_id,
        task_name=data.task_name,
        description=data.description,
        frequency=data.frequency,
        day_of_month=data.day_of_month,
        day_of_week=data.day_of_week,
        priority=data.priority,
        assignee_id=data.assignee_id,
    )
    db.add(task)
    await db.flush()

    await log_activity(
        db, user.id, "create", "recurring_task", data.task_name,
        project_id=project_id, team_id=project.team_id,
        detail=f"{data.frequency} / {data.priority}",
    )
    await db.commit()
    await db.refresh(task)
    return task


async def list_recurring_tasks(
    db: AsyncSession, user, project_id: int,
) -> list[RecurringTask]:
    """프로젝트별 반복 업무 목록"""
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    result = await db.execute(
        select(RecurringTask)
        .where(RecurringTask.project_id == project_id)
        .order_by(desc(RecurringTask.created_at))
    )
    return result.scalars().all()


async def update_recurring_task(
    db: AsyncSession, user, task_id: int, data,
) -> RecurringTask:
    """반복 업무 수정/비활성화"""
    task = await db.get(RecurringTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="반복 업무를 찾을 수 없습니다")

    # 프로젝트 접근 확인
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, task.project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="반복 업무를 찾을 수 없습니다")

    await check_team_permission(db, project.team_id, user.id, "task.update")

    updates = data.model_dump(exclude_unset=True)

    # 주기 변경 시 정합성 재검증
    if "frequency" in updates:
        _validate_frequency(data)

    for key, value in updates.items():
        setattr(task, key, value)

    await log_activity(
        db, user.id, "update", "recurring_task", task.task_name,
        project_id=task.project_id, team_id=project.team_id,
        detail=f"is_active={task.is_active}" if "is_active" in updates else None,
    )
    await db.commit()
    await db.refresh(task)
    return task


async def delete_recurring_task(
    db: AsyncSession, user, task_id: int,
) -> None:
    """반복 업무 삭제"""
    task = await db.get(RecurringTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="반복 업무를 찾을 수 없습니다")

    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, task.project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="반복 업무를 찾을 수 없습니다")

    await check_team_permission(db, project.team_id, user.id, "task.delete")

    name = task.task_name
    project_id = task.project_id
    await db.delete(task)

    await log_activity(
        db, user.id, "delete", "recurring_task", name,
        project_id=project_id, team_id=project.team_id,
    )
    await db.commit()
