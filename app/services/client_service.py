"""발주처(Client) 비즈니스 로직"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc, inspect as sa_inspect
from fastapi import HTTPException
import logging

from app.database import Client, Project, User, PaymentSchedule
from app.services.common import (
    get_user_team_ids, access_filter, check_team_permission,
    log_activity, get_accessible,
)

logger = logging.getLogger(__name__)


# ── 응답 보강 ──

async def enrich_list(db: AsyncSession, clients: list[Client]) -> list[dict]:
    if not clients:
        return []
    cids = [c.id for c in clients]

    # 활성 프로젝트 수
    r1 = await db.execute(
        select(Project.client_id, func.count())
        .where(Project.client_id.in_(cids), Project.status.in_(["planning", "active", "on_hold"]))
        .group_by(Project.client_id)
    )
    count_map = dict(r1.all())

    # 총 매출 (paid_amount 합계)
    r2 = await db.execute(
        select(Project.client_id, func.coalesce(func.sum(PaymentSchedule.paid_amount), 0))
        .join(PaymentSchedule, PaymentSchedule.project_id == Project.id)
        .where(Project.client_id.in_(cids), PaymentSchedule.status == "paid")
        .group_by(Project.client_id)
    )
    revenue_map = dict(r2.all())

    result = []
    for c in clients:
        d = {attr.key: getattr(c, attr.key) for attr in sa_inspect(Client).mapper.column_attrs}
        d["active_project_count"] = count_map.get(c.id, 0)
        d["total_revenue"] = revenue_map.get(c.id, 0)
        result.append(d)
    return result


async def enrich_one(db: AsyncSession, client: Client) -> dict:
    items = await enrich_list(db, [client])
    return items[0]


# ── CRUD ──

async def create(db: AsyncSession, user: User, data, team_id: int | None):
    team_ids = await get_user_team_ids(db, user.id)

    if team_id:
        if team_id not in team_ids:
            raise HTTPException(status_code=403, detail="해당 팀의 멤버가 아닙니다.")
        await check_team_permission(db, team_id, user.id, "client.create")

    # 중복 확인
    dup_filter = [Client.name == data.name, access_filter(Client, user.id, team_ids)]
    if team_id:
        dup_filter.append(Client.team_id == team_id)
    dup = await db.execute(select(Client).where(*dup_filter))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="이미 존재하는 발주처입니다")

    client = Client(user_id=user.id, team_id=team_id, **data.model_dump())
    db.add(client)
    await db.flush()
    await log_activity(db, user.id, "create", "client", data.name, team_id=team_id, client_id=client.id)
    await db.commit()
    await db.refresh(client)
    return client


async def get_list(
    db: AsyncSession, user: User, *,
    search: str = None, category: str = None,
    team_id: int = None, page: int = 1, size: int = 20,
):
    team_ids = await get_user_team_ids(db, user.id)

    if team_id:
        if team_id not in team_ids:
            raise HTTPException(status_code=403, detail="해당 팀의 멤버가 아닙니다.")
        access = Client.team_id == team_id
    else:
        access = access_filter(Client, user.id, team_ids)

    filters = [access]
    if search:
        filters.append(or_(
            Client.name.ilike(f"%{search}%"),
            Client.contact_name.ilike(f"%{search}%"),
            Client.contact_email.ilike(f"%{search}%"),
        ))
    if category:
        filters.append(Client.category == category)

    total = (await db.execute(
        select(func.count()).select_from(Client).where(*filters)
    )).scalar()

    rows = (await db.execute(
        select(Client).where(*filters)
        .order_by(desc(Client.created_at))
        .offset((page - 1) * size).limit(size)
    )).scalars().all()

    return rows, total


async def get_detail(db: AsyncSession, user: User, client_id: int):
    team_ids = await get_user_team_ids(db, user.id)
    client = await get_accessible(db, Client, client_id, user.id, team_ids)
    if not client:
        raise HTTPException(status_code=404, detail="발주처를 찾을 수 없습니다")
    return client


async def update(db: AsyncSession, user: User, client_id: int, data):
    team_ids = await get_user_team_ids(db, user.id)
    client = await get_accessible(db, Client, client_id, user.id, team_ids)
    if not client:
        raise HTTPException(status_code=404, detail="발주처를 찾을 수 없습니다")

    await check_team_permission(db, client.team_id, user.id, "client.update")

    fields = data.model_dump(exclude_unset=True)

    if "name" in fields and fields["name"] != client.name:
        dup = await db.execute(select(Client).where(
            access_filter(Client, user.id, team_ids),
            Client.name == fields["name"], Client.id != client_id,
        ))
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="이미 존재하는 발주처입니다")

    for k, v in fields.items():
        setattr(client, k, v)

    await log_activity(
        db, user.id, "update", "client", client.name,
        team_id=client.team_id, client_id=client.id,
        detail=f"변경: {', '.join(fields.keys())}",
    )
    await db.commit()
    await db.refresh(client)
    return client


async def delete(db: AsyncSession, user: User, client_id: int):
    team_ids = await get_user_team_ids(db, user.id)
    client = await get_accessible(db, Client, client_id, user.id, team_ids)
    if not client:
        raise HTTPException(status_code=404, detail="발주처를 찾을 수 없습니다")

    await check_team_permission(db, client.team_id, user.id, "client.delete")

    cnt = (await db.execute(
        select(func.count()).select_from(Project).where(Project.client_id == client_id)
    )).scalar()
    if cnt > 0:
        raise HTTPException(status_code=400, detail="연관 프로젝트가 있어 삭제할 수 없습니다")

    await log_activity(db, user.id, "delete", "client", client.name, team_id=client.team_id, client_id=client.id)
    await db.delete(client)
    await db.commit()


async def get_projects(
    db: AsyncSession, user: User, client_id: int, *, page: int = 1, size: int = 20,
):
    # 발주처 접근 확인
    team_ids = await get_user_team_ids(db, user.id)
    client = await get_accessible(db, Client, client_id, user.id, team_ids)
    if not client:
        raise HTTPException(status_code=404, detail="발주처를 찾을 수 없습니다")

    filters = [Project.client_id == client_id]

    total = (await db.execute(
        select(func.count()).select_from(Project).where(*filters)
    )).scalar()

    rows = (await db.execute(
        select(Project).where(*filters)
        .order_by(desc(Project.created_at))
        .offset((page - 1) * size).limit(size)
    )).scalars().all()

    return rows, total
