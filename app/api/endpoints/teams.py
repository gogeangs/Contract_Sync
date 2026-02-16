from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import logging

from app.database import get_db, User, Team, TeamMember, utc_now
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic 모델
class TeamCreate(BaseModel):
    name: str
    description: Optional[str] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class MemberInvite(BaseModel):
    email: str


class MemberRoleUpdate(BaseModel):
    role: str  # admin, member


# ============ 헬퍼 함수 ============

async def get_team_member(db: AsyncSession, team_id: int, user_id: int) -> Optional[TeamMember]:
    """팀 멤버 조회"""
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def require_team_role(db: AsyncSession, team_id: int, user_id: int, roles: list[str]) -> TeamMember:
    """특정 역할 이상의 팀 멤버인지 확인"""
    member = await get_team_member(db, team_id, user_id)
    if not member or member.role not in roles:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")
    return member


# ============ 팀 CRUD ============

@router.post("")
@limiter.limit("10/minute")
async def create_team(
    data: TeamCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """팀 생성"""
    user = await require_current_user(request, db)

    if not data.name or not data.name.strip():
        raise HTTPException(status_code=400, detail="팀 이름을 입력해주세요.")

    team = Team(
        name=data.name.strip(),
        description=data.description,
        created_by=user.id,
    )
    db.add(team)
    await db.flush()

    # 생성자를 owner로 추가
    owner = TeamMember(team_id=team.id, user_id=user.id, role="owner")
    db.add(owner)
    await db.commit()
    await db.refresh(team)

    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
        "role": "owner",
        "created_at": team.created_at.isoformat() if team.created_at else None,
    }


@router.get("")
async def list_teams(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """내가 속한 팀 목록"""
    user = await require_current_user(request, db)

    result = await db.execute(
        select(Team, TeamMember.role)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id)
        .order_by(Team.created_at)
    )
    rows = result.all()

    return [
        {
            "id": team.id,
            "name": team.name,
            "description": team.description,
            "role": role,
            "created_at": team.created_at.isoformat() if team.created_at else None,
        }
        for team, role in rows
    ]


@router.get("/{team_id}")
async def get_team(
    team_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """팀 상세 + 멤버 목록"""
    user = await require_current_user(request, db)

    member = await get_team_member(db, team_id, user.id)
    if not member:
        raise HTTPException(status_code=403, detail="팀 멤버가 아닙니다.")

    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")

    # 멤버 목록
    members_result = await db.execute(
        select(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == team_id)
        .order_by(TeamMember.joined_at)
    )
    members = [
        {
            "user_id": u.id,
            "email": u.email,
            "name": u.name,
            "role": tm.role,
            "joined_at": tm.joined_at.isoformat() if tm.joined_at else None,
        }
        for tm, u in members_result.all()
    ]

    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "my_role": member.role,
        "members": members,
    }


@router.put("/{team_id}")
@limiter.limit("10/minute")
async def update_team(
    team_id: int,
    data: TeamUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """팀 정보 수정 (owner/admin)"""
    user = await require_current_user(request, db)
    await require_team_role(db, team_id, user.id, ["owner", "admin"])

    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")

    if data.name is not None:
        team.name = data.name.strip()
    if data.description is not None:
        team.description = data.description

    await db.commit()
    await db.refresh(team)

    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
    }


@router.delete("/{team_id}")
async def delete_team(
    team_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """팀 삭제 (owner만)"""
    user = await require_current_user(request, db)
    await require_team_role(db, team_id, user.id, ["owner"])

    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")

    await db.delete(team)
    await db.commit()

    return {"message": "팀이 삭제되었습니다."}


# ============ 멤버 관리 ============

@router.post("/{team_id}/members")
@limiter.limit("10/minute")
async def invite_member(
    team_id: int,
    data: MemberInvite,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """멤버 초대 (이메일로)"""
    user = await require_current_user(request, db)
    await require_team_role(db, team_id, user.id, ["owner", "admin"])

    # 초대할 사용자 조회
    result = await db.execute(select(User).where(User.email == data.email))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="해당 이메일의 사용자를 찾을 수 없습니다.")

    # 이미 멤버인지 확인
    existing = await get_team_member(db, team_id, target_user.id)
    if existing:
        raise HTTPException(status_code=409, detail="이미 팀 멤버입니다.")

    member = TeamMember(team_id=team_id, user_id=target_user.id, role="member")
    db.add(member)
    await db.commit()

    return {
        "message": "멤버가 추가되었습니다.",
        "member": {
            "user_id": target_user.id,
            "email": target_user.email,
            "name": target_user.name,
            "role": "member",
        },
    }


@router.delete("/{team_id}/members/{target_user_id}")
async def remove_member(
    team_id: int,
    target_user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """멤버 제거"""
    user = await require_current_user(request, db)

    # owner는 제거 불가
    target_member = await get_team_member(db, team_id, target_user_id)
    if not target_member:
        raise HTTPException(status_code=404, detail="멤버를 찾을 수 없습니다.")

    if target_member.role == "owner":
        raise HTTPException(status_code=400, detail="팀 소유자는 제거할 수 없습니다.")

    # 본인이 나가거나, owner/admin이 제거
    if user.id != target_user_id:
        await require_team_role(db, team_id, user.id, ["owner", "admin"])

    await db.delete(target_member)
    await db.commit()

    return {"message": "멤버가 제거되었습니다."}


@router.patch("/{team_id}/members/{target_user_id}/role")
async def update_member_role(
    team_id: int,
    target_user_id: int,
    data: MemberRoleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """멤버 역할 변경 (owner만)"""
    user = await require_current_user(request, db)
    await require_team_role(db, team_id, user.id, ["owner"])

    if data.role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="역할은 admin 또는 member만 가능합니다.")

    target_member = await get_team_member(db, team_id, target_user_id)
    if not target_member:
        raise HTTPException(status_code=404, detail="멤버를 찾을 수 없습니다.")

    if target_member.role == "owner":
        raise HTTPException(status_code=400, detail="소유자의 역할은 변경할 수 없습니다.")

    target_member.role = data.role
    await db.commit()

    return {"message": "역할이 변경되었습니다.", "role": data.role}
