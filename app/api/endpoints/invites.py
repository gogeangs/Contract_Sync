"""4차 개발 Phase 1 — 미가입 사용자 이메일 초대 API"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from datetime import timedelta
import secrets
import logging

from app.database import (
    get_db, PendingInvite, Team, TeamMember, User, Notification, utc_now,
)
from app.api.endpoints.auth import require_current_user
from app.api.endpoints.teams import get_team_member

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Pydantic 모델 ──────────────────────────────

class InviteCreate(BaseModel):
    email: str = Field(..., max_length=255)
    role: str = Field("member", pattern=r'^(member|admin)$')


# ── 헬퍼 ──────────────────────────────────────

def _invite_to_dict(invite: PendingInvite, inviter_name: str = None) -> dict:
    return {
        "id": invite.id,
        "team_id": invite.team_id,
        "email": invite.email,
        "role": invite.role,
        "status": invite.status,
        "invited_by": invite.invited_by,
        "inviter_name": inviter_name,
        "created_at": invite.created_at.isoformat() if invite.created_at else None,
        "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
    }


async def _send_invite_email(invite: PendingInvite, team: Team, inviter: User, base_url: str):
    """초대 이메일 발송"""
    try:
        from html import escape
        from app.services.email_service import send_email
        accept_url = f"{base_url}/api/v1/invites/accept/{invite.token}"

        # XSS 방지: 사용자 입력값 HTML 이스케이프
        safe_inviter = escape(inviter.name or inviter.email)
        safe_team = escape(team.name)
        safe_role = escape(invite.role)

        html = f"""
        <div style="font-family: 'Pretendard', sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #4F46E5, #7C3AED); padding: 32px; border-radius: 12px 12px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 24px;">Contract Sync</h1>
            </div>
            <div style="background: white; padding: 32px; border: 1px solid #E5E7EB; border-top: none; border-radius: 0 0 12px 12px;">
                <h2 style="color: #1F2937; margin-top: 0;">팀 초대</h2>
                <p style="color: #4B5563; line-height: 1.6;">
                    안녕하세요,<br>
                    <strong>{safe_inviter}</strong>님이 Contract Sync의
                    "<strong>{safe_team}</strong>" 팀에 초대했습니다.
                </p>
                <p style="color: #4B5563;">아래 버튼을 클릭하여 팀에 합류하세요.</p>
                <div style="text-align: center; margin: 32px 0;">
                    <a href="{accept_url}"
                       style="background: #4F46E5; color: white; padding: 14px 32px;
                              border-radius: 8px; text-decoration: none; font-weight: 600;
                              display: inline-block;">
                        팀 합류하기
                    </a>
                </div>
                <p style="color: #9CA3AF; font-size: 14px;">
                    이 초대는 7일 후 만료됩니다.<br>
                    역할: {safe_role}
                </p>
            </div>
        </div>
        """

        await send_email(
            to_email=invite.email,
            subject=f"[Contract Sync] {team.name} 팀에 초대되었습니다",
            html_body=html,
        )
        logger.info(f"초대 이메일 발송: {invite.email} → {team.name}")
    except Exception as e:
        logger.warning(f"초대 이메일 발송 실패: {e}")


# ── API 엔드포인트 ─────────────────────────────

@router.post("/teams/{team_id}/invites")
async def create_invite(
    team_id: int,
    body: InviteCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """초대 발송 (owner/admin)"""
    member = await get_team_member(db, team_id, current_user.id)
    if not member or member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="초대 권한이 없습니다.")

    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")

    # 이미 가입된 사용자 확인
    existing_user = await db.execute(
        select(User).where(User.email == body.email)
    )
    existing = existing_user.scalar_one_or_none()
    if existing:
        # 이미 팀 멤버인지 확인
        existing_member = await get_team_member(db, team_id, existing.id)
        if existing_member:
            raise HTTPException(status_code=400, detail="이미 팀에 소속된 멤버입니다.")

    # 대기 중인 동일 이메일 초대 확인
    pending = await db.execute(
        select(PendingInvite).where(
            PendingInvite.team_id == team_id,
            PendingInvite.email == body.email,
            PendingInvite.status == "pending",
        )
    )
    if pending.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 대기 중인 초대가 있습니다.")

    invite = PendingInvite(
        team_id=team_id,
        email=body.email,
        role=body.role,
        token=secrets.token_urlsafe(48),
        invited_by=current_user.id,
        expires_at=utc_now() + timedelta(days=7),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    # 이메일 발송
    base_url = str(request.base_url).rstrip("/")
    await _send_invite_email(invite, team, current_user, base_url)

    return _invite_to_dict(invite, current_user.name)


@router.get("/teams/{team_id}/invites")
async def list_invites(
    team_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """대기 초대 목록"""
    member = await get_team_member(db, team_id, current_user.id)
    if not member or member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="조회 권한이 없습니다.")

    # 만료된 초대 상태 업데이트
    result = await db.execute(
        select(PendingInvite).where(
            PendingInvite.team_id == team_id,
            PendingInvite.status == "pending",
            PendingInvite.expires_at < utc_now(),
        )
    )
    for inv in result.scalars().all():
        inv.status = "expired"
    await db.commit()

    # 전체 목록 조회
    result = await db.execute(
        select(PendingInvite, User)
        .join(User, PendingInvite.invited_by == User.id)
        .where(PendingInvite.team_id == team_id)
        .order_by(PendingInvite.created_at.desc())
    )
    return [_invite_to_dict(inv, u.name) for inv, u in result.all()]


@router.delete("/invites/{invite_id}")
async def cancel_invite(
    invite_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """초대 취소"""
    invite = await db.get(PendingInvite, invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="초대를 찾을 수 없습니다.")

    member = await get_team_member(db, invite.team_id, current_user.id)
    if not member or member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="취소 권한이 없습니다.")

    if invite.status != "pending":
        raise HTTPException(status_code=400, detail="대기 중인 초대만 취소할 수 있습니다.")

    invite.status = "expired"
    await db.commit()
    return {"ok": True}


@router.get("/invites/accept/{token}")
async def get_invite_info(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """초대 수락 페이지 정보 (비로그인)"""
    result = await db.execute(
        select(PendingInvite, Team)
        .join(Team, PendingInvite.team_id == Team.id)
        .where(PendingInvite.token == token)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="초대를 찾을 수 없습니다.")

    invite, team = row

    # 만료 확인
    if invite.status != "pending" or invite.expires_at < utc_now():
        if invite.status == "pending":
            invite.status = "expired"
            await db.commit()
        return {
            "status": invite.status,
            "team_name": team.name,
            "expired": True,
        }

    inviter = await db.get(User, invite.invited_by)
    return {
        "status": "pending",
        "team_name": team.name,
        "team_description": team.description,
        "inviter_name": inviter.name if inviter else None,
        "email": invite.email,
        "role": invite.role,
        "expired": False,
        "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
    }


@router.post("/invites/accept/{token}")
async def accept_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """초대 수락 (로그인 필요)"""
    result = await db.execute(
        select(PendingInvite).where(PendingInvite.token == token)
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="초대를 찾을 수 없습니다.")

    if invite.status != "pending":
        raise HTTPException(status_code=400, detail="이미 처리된 초대입니다.")

    if invite.expires_at < utc_now():
        invite.status = "expired"
        await db.commit()
        raise HTTPException(status_code=400, detail="만료된 초대입니다.")

    # 이미 팀 멤버인지 확인
    existing = await get_team_member(db, invite.team_id, current_user.id)
    if existing:
        invite.status = "accepted"
        await db.commit()
        return {"ok": True, "message": "이미 팀에 소속되어 있습니다."}

    # 팀 멤버 추가
    new_member = TeamMember(
        team_id=invite.team_id,
        user_id=current_user.id,
        role=invite.role,
    )
    db.add(new_member)

    invite.status = "accepted"

    # 초대자에게 알림
    team = await db.get(Team, invite.team_id)
    db.add(Notification(
        user_id=invite.invited_by,
        type="invite_accepted",
        title=f"{current_user.name or current_user.email}님이 팀에 합류했습니다",
        message=f"'{team.name}' 팀 초대를 수락했습니다.",
        link=f"#/teams/{invite.team_id}",
    ))

    await db.commit()
    return {"ok": True, "team_id": invite.team_id, "team_name": team.name}
