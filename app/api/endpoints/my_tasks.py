"""4차 개발 Phase 2 — 멀티팀 우선업무 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import logging

from app.database import (
    get_db, Task, TeamMember, Team, Project, User, UserTaskPriority,
)
from app.api.endpoints.auth import require_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class PriorityUpdate(BaseModel):
    """우선순위 순서 저장"""
    task_ids: list[int]  # 순서대로 정렬된 task_id 목록


@router.get("/my/tasks")
async def list_my_tasks(
    team_id: Optional[int] = Query(None, description="특정 팀 필터"),
    status: Optional[str] = Query(None, description="상태 필터"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """전체 팀 통합 내 업무 목록"""
    # 소속 팀 조회
    teams_result = await db.execute(
        select(TeamMember.team_id, Team.name)
        .join(Team, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == current_user.id)
    )
    my_teams = {t_id: t_name for t_id, t_name in teams_result.all()}

    if not my_teams:
        return {"items": [], "teams": []}

    # 업무 조회
    query = (
        select(Task, Project.project_name, Project.team_id)
        .join(Project, Task.project_id == Project.id)
        .where(Task.assignee_id == current_user.id)
    )

    if team_id:
        if team_id not in my_teams:
            raise HTTPException(status_code=403, detail="소속 팀이 아닙니다.")
        query = query.where(Project.team_id == team_id)
    else:
        query = query.where(Project.team_id.in_(my_teams.keys()))

    if status:
        query = query.where(Task.status == status)
    else:
        # 기본: 완료/취소 제외
        query = query.where(Task.status.notin_(["완료", "취소"]))

    result = await db.execute(query)
    tasks_data = result.all()

    # 개인 우선순위 조회
    task_ids = [t.id for t, _, _ in tasks_data]
    priorities = {}
    if task_ids:
        prio_result = await db.execute(
            select(UserTaskPriority)
            .where(
                UserTaskPriority.user_id == current_user.id,
                UserTaskPriority.task_id.in_(task_ids),
            )
        )
        priorities = {p.task_id: p.sort_order for p in prio_result.scalars().all()}

    items = []
    for task, project_name, task_team_id in tasks_data:
        items.append({
            "id": task.id,
            "task_name": task.task_name,
            "status": task.status,
            "priority": task.priority,
            "due_date": task.due_date,
            "project_id": task.project_id,
            "project_name": project_name,
            "team_id": task_team_id,
            "team_name": my_teams.get(task_team_id, ""),
            "sort_order": priorities.get(task.id, 9999),
            "created_at": task.created_at.isoformat() if task.created_at else None,
        })

    # 우선순위 정렬 (sort_order → due_date)
    items.sort(key=lambda x: (x["sort_order"], x["due_date"] or "9999-99-99"))

    teams_list = [{"id": tid, "name": tname} for tid, tname in my_teams.items()]
    return {"items": items, "teams": teams_list}


@router.put("/my/tasks/priority")
async def update_priority(
    body: PriorityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """우선순위 순서 저장"""
    # 기존 우선순위 삭제
    existing = await db.execute(
        select(UserTaskPriority).where(UserTaskPriority.user_id == current_user.id)
    )
    for p in existing.scalars().all():
        await db.delete(p)

    # 새 우선순위 저장
    for idx, task_id in enumerate(body.task_ids):
        db.add(UserTaskPriority(
            user_id=current_user.id,
            task_id=task_id,
            sort_order=idx,
        ))

    await db.commit()
    return {"ok": True, "count": len(body.task_ids)}
