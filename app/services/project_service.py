"""프로젝트(Project) 비즈니스 로직"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, inspect as sa_inspect
from fastapi import HTTPException
import logging

from app.database import (
    Project, Client, Task, Document, User, TeamMember,
    Notification, ProjectTemplate,
)
from app.services.common import (
    get_user_team_ids, access_filter, check_team_permission,
    log_activity, get_accessible,
)

logger = logging.getLogger(__name__)

# 상태 전이 규칙
VALID_STATUS_TRANSITIONS = {
    "planning": {"active"},
    "active": {"on_hold", "completed", "cancelled"},
    "on_hold": {"active", "completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


# ── 프로젝트 고유 헬퍼 ──

async def _notify_team(
    db: AsyncSession, project: Project, sender_id: int,
    ntype: str, title: str, message: str = None,
):
    if not project.team_id:
        return
    result = await db.execute(
        select(TeamMember.user_id).where(
            TeamMember.team_id == project.team_id,
            TeamMember.user_id != sender_id,
        )
    )
    import json
    for (uid,) in result.all():
        db.add(Notification(
            user_id=uid, type=ntype, title=title, message=message,
            link=json.dumps({"project_id": project.id}),
        ))


# ── 응답 보강 ──

async def enrich_list(db: AsyncSession, projects: list) -> list[dict]:
    if not projects:
        return []
    pids = [p.id for p in projects]

    # 업무 수
    r1 = await db.execute(
        select(Task.project_id, func.count())
        .where(Task.project_id.in_(pids))
        .group_by(Task.project_id)
    )
    task_map = dict(r1.all())

    # 완료 업무 수
    r2 = await db.execute(
        select(Task.project_id, func.count())
        .where(Task.project_id.in_(pids), Task.status.in_(["completed", "confirmed"]))
        .group_by(Task.project_id)
    )
    done_map = dict(r2.all())

    # 문서 수
    r3 = await db.execute(
        select(Document.project_id, func.count())
        .where(Document.project_id.in_(pids))
        .group_by(Document.project_id)
    )
    doc_map = dict(r3.all())

    # 발주처 이름
    cids = list({p.client_id for p in projects if p.client_id})
    name_map = {}
    if cids:
        r4 = await db.execute(select(Client.id, Client.name).where(Client.id.in_(cids)))
        name_map = dict(r4.all())

    result = []
    for p in projects:
        d = {attr.key: getattr(p, attr.key) for attr in sa_inspect(Project).mapper.column_attrs}
        d["task_count"] = task_map.get(p.id, 0)
        d["completed_task_count"] = done_map.get(p.id, 0)
        d["document_count"] = doc_map.get(p.id, 0)
        d["client_name"] = name_map.get(p.client_id) if p.client_id else None
        result.append(d)
    return result


async def enrich_one(db: AsyncSession, project: Project) -> dict:
    return (await enrich_list(db, [project]))[0]


# ── CRUD ──

async def create(db: AsyncSession, user: User, data, team_id: int | None):
    team_ids = await get_user_team_ids(db, user.id)

    if team_id:
        if team_id not in team_ids:
            raise HTTPException(status_code=403, detail="해당 팀의 멤버가 아닙니다.")
        await check_team_permission(db, team_id, user.id, "project.create")

    # outsourcing → client_id 필수
    if data.project_type == "outsourcing" and not data.client_id:
        raise HTTPException(status_code=400, detail="외주 프로젝트는 발주처 지정이 필수입니다")

    # client_id 유효성
    if data.client_id:
        c = await db.execute(select(Client).where(Client.id == data.client_id))
        if not c.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="발주처를 찾을 수 없습니다")

    project = Project(user_id=user.id, team_id=team_id, **data.model_dump())
    db.add(project)
    await db.flush()
    await log_activity(
        db, user.id, "create", "project", data.project_name,
        project_id=project.id, team_id=team_id, client_id=data.client_id,
    )
    await db.commit()
    await db.refresh(project)
    return project


async def get_list(
    db: AsyncSession, user: User, *,
    status: str = None, project_type: str = None, client_id: int = None,
    search: str = None, team_id: int = None, page: int = 1, size: int = 20,
):
    team_ids = await get_user_team_ids(db, user.id)

    if team_id:
        if team_id not in team_ids:
            raise HTTPException(status_code=403, detail="해당 팀의 멤버가 아닙니다.")
        access = Project.team_id == team_id
    else:
        access = access_filter(Project, user.id, team_ids)

    filters = [access]
    if status:
        filters.append(Project.status == status)
    if project_type:
        filters.append(Project.project_type == project_type)
    if client_id:
        filters.append(Project.client_id == client_id)
    if search:
        filters.append(Project.project_name.ilike(f"%{search}%"))

    total = (await db.execute(
        select(func.count()).select_from(Project).where(*filters)
    )).scalar()

    rows = (await db.execute(
        select(Project).where(*filters)
        .order_by(desc(Project.created_at))
        .offset((page - 1) * size).limit(size)
    )).scalars().all()

    return rows, total


async def get_detail(db: AsyncSession, user: User, project_id: int):
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    return project


async def update(db: AsyncSession, user: User, project_id: int, data):
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    await check_team_permission(db, project.team_id, user.id, "project.update")

    fields = data.model_dump(exclude_unset=True)

    # outsourcing 유형 변경 시 client_id 검증
    new_type = fields.get("project_type", project.project_type)
    new_client = fields.get("client_id", project.client_id)
    if new_type == "outsourcing" and not new_client:
        raise HTTPException(status_code=400, detail="외주 프로젝트는 발주처 지정이 필수입니다")

    if "client_id" in fields and fields["client_id"]:
        c = await db.execute(select(Client).where(Client.id == fields["client_id"]))
        if not c.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="발주처를 찾을 수 없습니다")

    for k, v in fields.items():
        setattr(project, k, v)

    await log_activity(
        db, user.id, "update", "project", project.project_name,
        project_id=project.id, team_id=project.team_id, client_id=project.client_id,
        detail=f"변경: {', '.join(fields.keys())}",
    )
    await db.commit()
    await db.refresh(project)
    return project


async def update_status(db: AsyncSession, user: User, project_id: int, new_status: str):
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    await check_team_permission(db, project.team_id, user.id, "project.update")

    allowed = VALID_STATUS_TRANSITIONS.get(project.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"'{project.status}' → '{new_status}' 상태 변경이 불가합니다",
        )

    old_status = project.status
    project.status = new_status

    await log_activity(
        db, user.id, "status_change", "project", project.project_name,
        project_id=project.id, team_id=project.team_id,
        detail=f"{old_status} → {new_status}",
    )
    await _notify_team(
        db, project, user.id, "status_change",
        f"프로젝트 '{project.project_name}' 상태: {old_status} → {new_status}",
    )
    await db.commit()
    await db.refresh(project)
    return project


async def delete(db: AsyncSession, user: User, project_id: int):
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    await check_team_permission(db, project.team_id, user.id, "project.delete")

    await log_activity(
        db, user.id, "delete", "project", project.project_name,
        project_id=project.id, team_id=project.team_id,
    )
    await db.delete(project)
    await db.commit()


async def create_from_template(db: AsyncSession, user: User, template_id: int, team_id: int | None):
    """템플릿에서 프로젝트 + 업무 일괄 생성"""
    team_ids = await get_user_team_ids(db, user.id)

    if team_id:
        if team_id not in team_ids:
            raise HTTPException(status_code=403, detail="해당 팀의 멤버가 아닙니다.")
        await check_team_permission(db, team_id, user.id, "project.create")

    tmpl = (await db.execute(
        select(ProjectTemplate).where(ProjectTemplate.id == template_id)
    )).scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다")

    # 프로젝트 생성
    name = f"{tmpl.name} (사본)"
    project = Project(
        user_id=user.id, team_id=team_id,
        project_name=name,
        project_type=tmpl.project_type,
        description=tmpl.description,
    )
    db.add(project)
    await db.flush()

    # 업무 일괄 생성
    for t in (tmpl.task_templates or []):
        task = Task(
            user_id=user.id, team_id=team_id, project_id=project.id,
            task_name=t.get("task_name", ""),
            phase=t.get("phase"),
            priority=t.get("priority", "보통"),
            is_client_facing=t.get("is_client_facing", False),
        )
        db.add(task)
        await db.flush()
        task.task_code = f"TASK-{task.id:03d}"

    await log_activity(
        db, user.id, "create", "project", project.project_name,
        project_id=project.id, team_id=team_id,
        detail=f"템플릿 '{tmpl.name}'에서 생성",
    )
    await db.commit()
    await db.refresh(project)
    return project
