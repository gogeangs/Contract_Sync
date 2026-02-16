from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, or_
from typing import Optional
import logging

from app.database import get_db, User, ActivityLog, TeamMember
from app.api.endpoints.auth import require_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_activities(
    request: Request,
    contract_id: Optional[int] = Query(None, description="계약 ID 필터"),
    team_id: Optional[int] = Query(None, description="팀 ID 필터"),
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """활동 로그 조회"""
    user = await require_current_user(request, db)

    # 사용자가 접근 가능한 활동만 조회
    # (본인의 활동 + 본인이 속한 팀의 활동)
    team_ids_result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    user_team_ids = [row[0] for row in team_ids_result.all()]

    conditions = [ActivityLog.user_id == user.id]
    if user_team_ids:
        conditions.append(ActivityLog.team_id.in_(user_team_ids))
    access_filter = or_(*conditions)

    query = select(ActivityLog, User).join(User, User.id == ActivityLog.user_id).where(access_filter)

    if contract_id is not None:
        query = query.where(ActivityLog.contract_id == contract_id)
    if team_id is not None:
        if team_id not in user_team_ids:
            raise HTTPException(status_code=403, detail="팀 멤버가 아닙니다")
        query = query.where(ActivityLog.team_id == team_id)

    # 전체 개수
    count_conditions = [access_filter]
    if contract_id is not None:
        count_conditions.append(ActivityLog.contract_id == contract_id)
    if team_id is not None:
        count_conditions.append(ActivityLog.team_id == team_id)

    count_q = select(func.count()).select_from(ActivityLog).where(*count_conditions)
    total = (await db.execute(count_q)).scalar()

    # 페이지네이션
    result = await db.execute(
        query.order_by(desc(ActivityLog.created_at))
        .offset((page - 1) * size)
        .limit(size)
    )
    rows = result.all()

    return {
        "items": [
            {
                "id": log.id,
                "contract_id": log.contract_id,
                "team_id": log.team_id,
                "user_id": log.user_id,
                "user_name": u.name or u.email,
                "user_picture": u.picture,
                "action": log.action,
                "target_type": log.target_type,
                "target_name": log.target_name,
                "detail": log.detail,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log, u in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }
