from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from typing import Optional
import json as json_mod
import logging

from app.database import get_db, User, Team, TeamMember, ActivityLog, Notification, TEAM_PERMISSIONS, utc_now
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter


def check_permission(role: str, permission: str) -> bool:
    """역할별 권한 확인"""
    return permission in TEAM_PERMISSIONS.get(role, set())

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic 모델
class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class MemberInvite(BaseModel):
    email: str = Field(..., max_length=255)


class MemberRoleUpdate(BaseModel):
    role: str = Field(..., pattern=r'^(admin|member|viewer)$')


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

    # 활동 로그
    db.add(ActivityLog(
        team_id=team.id, user_id=user.id,
        action="create", target_type="team", target_name=team.name,
    ))

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

    my_permissions = list(TEAM_PERMISSIONS.get(member.role, set()))

    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "my_role": member.role,
        "my_permissions": my_permissions,
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

    # 활동 로그
    db.add(ActivityLog(
        team_id=team_id, user_id=user.id,
        action="invite", target_type="member",
        target_name=target_user.name or target_user.email,
    ))

    # 초대 알림
    db.add(Notification(
        user_id=target_user.id,
        type="team_invite",
        title=f"{user.name or user.email}님이 팀에 초대했습니다",
        message=f"팀에 초대되었습니다.",
        link=json_mod.dumps({"team_id": team_id}),
    ))

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

    # H-5: owner 제거 방지 + 마지막 owner 탈퇴 방지
    if target_member.role == "owner":
        # 다른 owner가 있는지 확인
        owner_count_result = await db.execute(
            select(func.count()).select_from(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.role == "owner",
            )
        )
        owner_count = owner_count_result.scalar()
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="팀의 마지막 소유자는 제거할 수 없습니다. 먼저 다른 멤버를 소유자로 지정하세요.")

    # 본인이 나가거나, owner/admin이 제거
    if user.id != target_user_id:
        await require_team_role(db, team_id, user.id, ["owner", "admin"])

    # 활동 로그
    target_result = await db.execute(select(User).where(User.id == target_user_id))
    target_u = target_result.scalar_one_or_none()
    db.add(ActivityLog(
        team_id=team_id, user_id=user.id,
        action="remove", target_type="member",
        target_name=target_u.name or target_u.email if target_u else str(target_user_id),
    ))

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

    # L-4: TEAM_PERMISSIONS 기반 역할 검증 (owner 제외)
    allowed_roles = {r for r in TEAM_PERMISSIONS if r != "owner"}
    if data.role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"역할은 {', '.join(sorted(allowed_roles))}만 가능합니다.")

    target_member = await get_team_member(db, team_id, target_user_id)
    if not target_member:
        raise HTTPException(status_code=404, detail="멤버를 찾을 수 없습니다.")

    if target_member.role == "owner":
        raise HTTPException(status_code=400, detail="소유자의 역할은 변경할 수 없습니다.")

    old_role = target_member.role
    target_member.role = data.role

    # 활동 로그
    target_result = await db.execute(select(User).where(User.id == target_user_id))
    target_u = target_result.scalar_one_or_none()
    db.add(ActivityLog(
        team_id=team_id, user_id=user.id,
        action="change_role", target_type="member",
        target_name=target_u.name or target_u.email if target_u else str(target_user_id),
        detail=f"{old_role} -> {data.role}",
    ))

    await db.commit()

    return {"message": "역할이 변경되었습니다.", "role": data.role}


# ============ 권한 확인 API ============

@router.get("/{team_id}/permissions")
async def get_my_permissions(
    team_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """내 팀 권한 조회"""
    user = await require_current_user(request, db)
    member = await get_team_member(db, team_id, user.id)
    if not member:
        raise HTTPException(status_code=403, detail="팀 멤버가 아닙니다.")

    permissions = list(TEAM_PERMISSIONS.get(member.role, set()))
    return {
        "role": member.role,
        "permissions": permissions,
    }
