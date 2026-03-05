from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, or_
from typing import Optional
import logging

from app.database import get_db, User, ActivityLog, Project
from app.api.endpoints.auth import require_current_user
from app.services.common import get_user_team_ids

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_activities(
    request: Request,
    project_id: Optional[int] = Query(None, description="프로젝트 ID 필터"),
    team_id: Optional[int] = Query(None, description="팀 ID 필터"),
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """활동 로그 조회"""
    user = await require_current_user(request, db)

    # 사용자가 접근 가능한 활동만 조회
    # (본인의 활동 + 본인이 속한 팀의 활동)
    user_team_ids = await get_user_team_ids(db, user.id)

    conditions = [ActivityLog.user_id == user.id]
    if user_team_ids:
        conditions.append(ActivityLog.team_id.in_(user_team_ids))
    access_filter = or_(*conditions)

    query = select(ActivityLog, User).join(User, User.id == ActivityLog.user_id).where(access_filter)

    # project_id 필터 시 해당 프로젝트 접근 권한 검증
    if project_id is not None:
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
        # 본인 프로젝트이거나 팀 프로젝트(소속 팀)인지 확인
        if project.team_id:
            if project.team_id not in user_team_ids:
                raise HTTPException(status_code=403, detail="해당 프로젝트에 접근 권한이 없습니다")
        elif project.user_id != user.id:
            raise HTTPException(status_code=403, detail="해당 프로젝트에 접근 권한이 없습니다")
        query = query.where(ActivityLog.project_id == project_id)
    if team_id is not None:
        if team_id not in user_team_ids:
            raise HTTPException(status_code=403, detail="팀 멤버가 아닙니다")
        query = query.where(ActivityLog.team_id == team_id)

    # 전체 개수
    count_conditions = [access_filter]
    if project_id is not None:
        count_conditions.append(ActivityLog.project_id == project_id)
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
                "project_id": log.project_id,
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
