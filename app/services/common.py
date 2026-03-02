"""서비스 공통 헬퍼 — get_user_team_ids, access_filter, check_team_permission, log_activity, get_accessible"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from fastapi import HTTPException
import logging

from app.database import TeamMember, ActivityLog, TEAM_PERMISSIONS

logger = logging.getLogger(__name__)


async def get_user_team_ids(db: AsyncSession, user_id: int) -> list[int]:
    """사용자가 속한 팀 ID 목록 조회"""
    result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user_id)
    )
    return [row[0] for row in result.all()]


def access_filter(model, user_id: int, team_ids: list[int]):
    """개인 + 팀 접근 필터 (범용). model에 user_id, team_id 컬럼이 있어야 한다."""
    conditions = [
        (model.user_id == user_id) & (model.team_id == None)  # noqa: E711
    ]
    if team_ids:
        conditions.append(model.team_id.in_(team_ids))
    return or_(*conditions)


async def check_team_permission(
    db: AsyncSession, team_id: int | None, user_id: int, permission: str,
):
    """팀 RBAC 권한 검사. team_id가 None이면 개인 소유이므로 통과."""
    if not team_id:
        return
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=403, detail="팀 멤버가 아닙니다.")
    if permission not in TEAM_PERMISSIONS.get(member.role, set()):
        raise HTTPException(status_code=403, detail="해당 작업에 대한 권한이 없습니다.")


async def log_activity(
    db: AsyncSession, user_id: int, action: str, target_type: str,
    target_name: str, *, project_id: int = None, team_id: int = None,
    client_id: int = None, detail: str = None,
):
    """활동 로그 기록 (실패해도 예외 전파하지 않음)"""
    try:
        db.add(ActivityLog(
            project_id=project_id, team_id=team_id, user_id=user_id,
            client_id=client_id, action=action, target_type=target_type,
            target_name=target_name, detail=detail,
        ))
    except Exception as e:
        logger.warning(f"활동 로그 기록 실패: {e}")


async def get_accessible(
    db: AsyncSession, model, entity_id: int, user_id: int, team_ids: list[int],
):
    """범용 접근 가능 엔티티 조회. model.id == entity_id + access_filter 적용."""
    result = await db.execute(
        select(model).where(
            model.id == entity_id,
            access_filter(model, user_id, team_ids),
        )
    )
    return result.scalar_one_or_none()
