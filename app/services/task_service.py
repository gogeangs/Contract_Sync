"""업무(Task) 비즈니스 로직"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, inspect as sa_inspect
from fastapi import HTTPException
from pathlib import Path
import uuid
import shutil
import logging

from app.database import (
    Task, TaskAttachment, Project, Client, User, TeamMember,
    Notification, utc_now,
)
from app.services.common import (
    get_user_team_ids, access_filter, check_team_permission,
    log_activity, get_accessible,
)

logger = logging.getLogger(__name__)

ATTACHMENTS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "attachments"
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

# 상태 전이 규칙
VALID_STATUS_TRANSITIONS = {
    "pending": {"in_progress"},
    "in_progress": {"pending", "completed"},
    "completed": {"in_progress", "report_sent"},
    "report_sent": {"feedback_pending"},
    "feedback_pending": {"confirmed", "revision_requested"},
    "revision_requested": {"in_progress"},
    "confirmed": set(),
}


# ── 업무 고유 헬퍼 ──

async def _notify_assignee(
    db: AsyncSession, task: Task, sender: User,
    ntype: str, title: str, message: str = None,
):
    import json
    if task.assignee_id and task.assignee_id != sender.id:
        db.add(Notification(
            user_id=task.assignee_id, type=ntype, title=title, message=message,
            link=json.dumps({"task_id": task.id, "project_id": task.project_id}),
        ))


async def _resolve_assignee(db: AsyncSession, assignee_id: int | None, team_id: int | None):
    """담당자 유효성 검증 + 이름 조회"""
    if not assignee_id:
        return None, None

    if team_id:
        m = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == assignee_id,
            )
        )
        if not m.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="팀 멤버만 담당자로 지정할 수 있습니다")

    u = (await db.execute(select(User).where(User.id == assignee_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다")
    return u.id, u.name or u.email


# ── 응답 보강 ──

async def enrich_list(db: AsyncSession, tasks: list) -> list[dict]:
    if not tasks:
        return []
    tids = [t.id for t in tasks]

    # 산출물 수
    r1 = await db.execute(
        select(TaskAttachment.task_id, func.count())
        .where(TaskAttachment.task_id.in_(tids))
        .group_by(TaskAttachment.task_id)
    )
    att_map = dict(r1.all())

    # 담당자 이름
    aids = list({t.assignee_id for t in tasks if t.assignee_id})
    assignee_map = {}
    if aids:
        r2 = await db.execute(select(User.id, User.name).where(User.id.in_(aids)))
        assignee_map = {uid: name or "" for uid, name in r2.all()}

    # 프로젝트 이름
    pids = list({t.project_id for t in tasks if t.project_id})
    project_map = {}
    if pids:
        r3 = await db.execute(select(Project.id, Project.project_name).where(Project.id.in_(pids)))
        project_map = dict(r3.all())

    result = []
    for t in tasks:
        d = {attr.key: getattr(t, attr.key) for attr in sa_inspect(Task).mapper.column_attrs}
        d["attachment_count"] = att_map.get(t.id, 0)
        d["assignee_name"] = assignee_map.get(t.assignee_id) if t.assignee_id else None
        d["project_name"] = project_map.get(t.project_id) if t.project_id else None
        result.append(d)
    return result


async def enrich_one(db: AsyncSession, task: Task) -> dict:
    return (await enrich_list(db, [task]))[0]


# ── CRUD ──

async def create(db: AsyncSession, user: User, data, team_id: int | None):
    team_ids = await get_user_team_ids(db, user.id)

    effective_team_id = team_id

    if team_id:
        if team_id not in team_ids:
            raise HTTPException(status_code=403, detail="해당 팀의 멤버가 아닙니다.")
        await check_team_permission(db, team_id, user.id, "task.create")

    # project_id 유효성
    if data.project_id:
        p = (await db.execute(select(Project).where(Project.id == data.project_id))).scalar_one_or_none()
        if not p:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
        # 프로젝트에서 team_id 상속
        if not effective_team_id:
            effective_team_id = p.team_id

    # 담당자 검증
    _, _ = await _resolve_assignee(db, data.assignee_id, effective_team_id)

    task = Task(
        user_id=user.id,
        team_id=effective_team_id,
        **data.model_dump(),
    )
    db.add(task)
    await db.flush()
    task.task_code = f"TASK-{task.id:03d}"

    await log_activity(
        db, user.id, "create", "task", data.task_name,
        project_id=data.project_id, team_id=effective_team_id,
    )
    await db.commit()
    await db.refresh(task)
    return task


async def get_list(
    db: AsyncSession, user: User, *,
    project_id: int = None, status: str = None, assignee_id: int = None,
    priority: str = None, search: str = None,
    team_id: int = None, page: int = 1, size: int = 20,
):
    team_ids = await get_user_team_ids(db, user.id)

    if team_id:
        if team_id not in team_ids:
            raise HTTPException(status_code=403, detail="해당 팀의 멤버가 아닙니다.")
        access = Task.team_id == team_id
    else:
        access = access_filter(Task, user.id, team_ids)

    filters = [access]
    if project_id is not None:
        filters.append(Task.project_id == project_id)
    if status:
        filters.append(Task.status == status)
    if assignee_id:
        filters.append(Task.assignee_id == assignee_id)
    if priority:
        filters.append(Task.priority == priority)
    if search:
        filters.append(Task.task_name.ilike(f"%{search}%"))

    total = (await db.execute(
        select(func.count()).select_from(Task).where(*filters)
    )).scalar()

    rows = (await db.execute(
        select(Task).where(*filters)
        .order_by(Task.sort_order, desc(Task.created_at))
        .offset((page - 1) * size).limit(size)
    )).scalars().all()

    return rows, total


async def get_detail(db: AsyncSession, user: User, task_id: int):
    team_ids = await get_user_team_ids(db, user.id)
    task = await get_accessible(db, Task, task_id, user.id, team_ids)
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")
    return task


async def update(db: AsyncSession, user: User, task_id: int, data):
    team_ids = await get_user_team_ids(db, user.id)
    task = await get_accessible(db, Task, task_id, user.id, team_ids)
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    await check_team_permission(db, task.team_id, user.id, "task.update")

    fields = data.model_dump(exclude_unset=True)
    for k, v in fields.items():
        setattr(task, k, v)

    await log_activity(
        db, user.id, "update", "task", task.task_name,
        project_id=task.project_id, team_id=task.team_id,
        detail=f"변경: {', '.join(fields.keys())}",
    )
    await db.commit()
    await db.refresh(task)
    return task


async def delete(db: AsyncSession, user: User, task_id: int):
    team_ids = await get_user_team_ids(db, user.id)
    task = await get_accessible(db, Task, task_id, user.id, team_ids)
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    await check_team_permission(db, task.team_id, user.id, "task.delete")

    # 산출물 파일 삭제
    att_dir = ATTACHMENTS_DIR / str(task_id)
    if att_dir.exists():
        shutil.rmtree(att_dir, ignore_errors=True)

    await log_activity(
        db, user.id, "delete", "task", task.task_name,
        project_id=task.project_id, team_id=task.team_id,
    )
    await db.delete(task)
    await db.commit()


async def update_status(db: AsyncSession, user: User, task_id: int, new_status: str):
    team_ids = await get_user_team_ids(db, user.id)
    task = await get_accessible(db, Task, task_id, user.id, team_ids)
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    await check_team_permission(db, task.team_id, user.id, "task.update")

    allowed = VALID_STATUS_TRANSITIONS.get(task.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"'{task.status}' → '{new_status}' 상태 변경이 불가합니다",
        )

    old_status = task.status
    task.status = new_status

    if new_status == "completed":
        task.completed_at = utc_now()
    elif old_status == "completed":
        task.completed_at = None

    await log_activity(
        db, user.id, "status_change", "task", task.task_name,
        project_id=task.project_id, team_id=task.team_id,
        detail=f"{old_status} → {new_status}",
    )
    await _notify_assignee(
        db, task, user, "status_change",
        f"업무 '{task.task_name}' 상태: {old_status} → {new_status}",
    )
    await db.commit()
    await db.refresh(task)
    return task


async def update_assignee(db: AsyncSession, user: User, task_id: int, assignee_id: int | None):
    team_ids = await get_user_team_ids(db, user.id)
    task = await get_accessible(db, Task, task_id, user.id, team_ids)
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    await check_team_permission(db, task.team_id, user.id, "task.assign")

    aid, aname = await _resolve_assignee(db, assignee_id, task.team_id)
    task.assignee_id = aid

    await log_activity(
        db, user.id, "assign", "task", task.task_name,
        project_id=task.project_id, team_id=task.team_id,
        detail=f"담당자: {aname or '없음'}",
    )

    # 담당자에게 알림
    if aid and aid != user.id:
        import json
        db.add(Notification(
            user_id=aid, type="assign",
            title=f"{user.name or user.email}님이 '{task.task_name}' 업무를 배정했습니다",
            link=json.dumps({"task_id": task.id, "project_id": task.project_id}),
        ))

    await db.commit()
    await db.refresh(task)
    return task


async def update_note(db: AsyncSession, user: User, task_id: int, note: str):
    team_ids = await get_user_team_ids(db, user.id)
    task = await get_accessible(db, Task, task_id, user.id, team_ids)
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    await check_team_permission(db, task.team_id, user.id, "task.update")
    task.note = note
    await db.commit()
    await db.refresh(task)
    return task


async def move_task(db: AsyncSession, user: User, task_id: int, target_project_id: int | None):
    team_ids = await get_user_team_ids(db, user.id)
    task = await get_accessible(db, Task, task_id, user.id, team_ids)
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    await check_team_permission(db, task.team_id, user.id, "task.update")

    old_project_id = task.project_id

    if target_project_id:
        project = await get_accessible(db, Project, target_project_id, user.id, team_ids)
        if not project:
            raise HTTPException(status_code=404, detail="대상 프로젝트를 찾을 수 없습니다")
        task.project_id = target_project_id
        task.team_id = project.team_id
    else:
        task.project_id = None

    await log_activity(
        db, user.id, "update", "task", task.task_name,
        project_id=target_project_id, team_id=task.team_id,
        detail=f"프로젝트 이동: {old_project_id} → {target_project_id}",
    )
    await db.commit()
    await db.refresh(task)
    return task


async def reorder(db: AsyncSession, user: User, task_orders: list[dict]):
    team_ids = await get_user_team_ids(db, user.id)

    for item in task_orders:
        tid = item.get("task_id")
        order = item.get("sort_order", 0)
        task = await get_accessible(db, Task, tid, user.id, team_ids)
        if task:
            task.sort_order = order

    await db.commit()
    return True


# ── 산출물(첨부파일) ──

async def upload_attachment(
    db: AsyncSession, user: User, task_id: int,
    file_name: str, file_content: bytes, mime_type: str,
):
    team_ids = await get_user_team_ids(db, user.id)
    task = await get_accessible(db, Task, task_id, user.id, team_ids)
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    await check_team_permission(db, task.team_id, user.id, "task.update")

    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="파일 크기는 20MB를 초과할 수 없습니다")

    # 파일 저장
    ext = Path(file_name).suffix
    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_dir = ATTACHMENTS_DIR / str(task_id)
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / saved_name

    save_path.write_bytes(file_content)

    att = TaskAttachment(
        task_id=task_id,
        file_name=Path(file_name).name,
        stored_path=str(save_path),
        file_size=len(file_content),
        mime_type=mime_type,
        uploaded_by=user.id,
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)
    return att


async def delete_attachment(db: AsyncSession, user: User, task_id: int, attachment_id: int):
    team_ids = await get_user_team_ids(db, user.id)
    task = await get_accessible(db, Task, task_id, user.id, team_ids)
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    await check_team_permission(db, task.team_id, user.id, "task.update")

    att = (await db.execute(
        select(TaskAttachment).where(
            TaskAttachment.id == attachment_id,
            TaskAttachment.task_id == task_id,
        )
    )).scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="산출물을 찾을 수 없습니다")

    # 파일 삭제
    p = Path(att.stored_path)
    if p.exists():
        p.unlink(missing_ok=True)

    await db.delete(att)
    await db.commit()


async def get_attachment(db: AsyncSession, user: User, task_id: int, attachment_id: int):
    team_ids = await get_user_team_ids(db, user.id)
    task = await get_accessible(db, Task, task_id, user.id, team_ids)
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    att = (await db.execute(
        select(TaskAttachment).where(
            TaskAttachment.id == attachment_id,
            TaskAttachment.task_id == task_id,
        )
    )).scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="산출물을 찾을 수 없습니다")

    p = Path(att.stored_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    return att, p
