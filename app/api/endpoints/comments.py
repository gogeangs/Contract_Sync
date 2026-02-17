from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, Field
from typing import Optional
import re
import json
import logging

from app.database import (
    get_db, User, Comment, Contract, TeamMember,
    Notification, ActivityLog, TEAM_PERMISSIONS, utc_now,
)
from app.api.endpoints.auth import require_current_user
from app.api.endpoints.contracts import _user_team_ids, _get_accessible_contract

logger = logging.getLogger(__name__)

router = APIRouter()


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    task_id: Optional[str] = Field(None, max_length=20)


class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


def _extract_mentions(content: str) -> list[str]:
    """@email 형식의 멘션 추출"""
    return re.findall(r'@([\w.+-]+@[\w-]+\.[\w.-]+)', content)


async def _notify_mentions(db: AsyncSession, mentions: list[str], comment: Comment, user: User, contract: Contract):
    """멘션된 사용자에게 알림 생성"""
    for email in set(mentions):
        result = await db.execute(select(User).where(User.email == email))
        target = result.scalar_one_or_none()
        if not target or target.id == user.id:
            continue

        notif = Notification(
            user_id=target.id,
            type="mention",
            title=f"{user.name or user.email}님이 회원님을 언급했습니다",
            message=comment.content[:100],
            link=json.dumps({"contract_id": contract.id, "task_id": comment.task_id}),
        )
        db.add(notif)


@router.get("/{contract_id}/comments")
async def list_comments(
    contract_id: int,
    task_id: Optional[str] = Query(None),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """계약/업무 댓글 목록 조회"""
    user = await require_current_user(request, db)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    query = select(Comment, User).join(User, User.id == Comment.user_id).where(
        Comment.contract_id == contract_id
    )
    if task_id is not None:
        query = query.where(Comment.task_id == task_id)
    else:
        query = query.where(Comment.task_id == None)  # noqa: E711

    query = query.order_by(Comment.created_at)
    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "id": c.id,
            "contract_id": c.contract_id,
            "task_id": c.task_id,
            "content": c.content,
            "user_id": u.id,
            "user_name": u.name or u.email,
            "user_picture": u.picture,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "is_mine": u.id == user.id,
        }
        for c, u in rows
    ]


@router.post("/{contract_id}/comments")
async def create_comment(
    contract_id: int,
    data: CommentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """댓글 작성"""
    user = await require_current_user(request, db)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    if not data.content or not data.content.strip():
        raise HTTPException(status_code=400, detail="댓글 내용을 입력해주세요.")

    # M-2: 댓글 길이 제한
    if len(data.content) > 5000:
        raise HTTPException(status_code=400, detail="댓글은 5000자를 초과할 수 없습니다.")

    comment = Comment(
        contract_id=contract_id,
        task_id=data.task_id,
        user_id=user.id,
        content=data.content.strip(),
    )
    db.add(comment)

    # 활동 로그
    task_name = ""
    if data.task_id and contract.tasks:
        for t in contract.tasks:
            if str(t.get("task_id")) == str(data.task_id):
                task_name = t.get("task_name", "")
                break

    log = ActivityLog(
        contract_id=contract_id,
        team_id=contract.team_id,
        user_id=user.id,
        action="comment",
        target_type="task" if data.task_id else "contract",
        target_name=task_name or contract.contract_name,
        detail=data.content[:200],
    )
    db.add(log)

    # @멘션 알림
    mentions = _extract_mentions(data.content)
    await _notify_mentions(db, mentions, comment, user, contract)

    # 팀 계약이면 팀 멤버에게 댓글 알림 (본인 제외)
    # M-4: N+1 쿼리 해결 - JOIN으로 한 번에 조회
    if contract.team_id:
        members_result = await db.execute(
            select(TeamMember.user_id, User.email)
            .join(User, User.id == TeamMember.user_id)
            .where(
                TeamMember.team_id == contract.team_id,
                TeamMember.user_id != user.id,
            )
        )
        mentioned_emails = set(mentions)
        for member_uid, member_email in members_result.all():
            if member_email not in mentioned_emails:
                notif = Notification(
                    user_id=member_uid,
                    type="comment",
                    title=f"{user.name or user.email}님이 댓글을 남겼습니다",
                    message=data.content[:100],
                    link=json.dumps({"contract_id": contract_id, "task_id": data.task_id}),
                )
                db.add(notif)

    await db.commit()
    await db.refresh(comment)

    return {
        "id": comment.id,
        "contract_id": comment.contract_id,
        "task_id": comment.task_id,
        "content": comment.content,
        "user_id": user.id,
        "user_name": user.name or user.email,
        "user_picture": user.picture,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
        "is_mine": True,
    }


@router.put("/{contract_id}/comments/{comment_id}")
async def update_comment(
    contract_id: int,
    comment_id: int,
    data: CommentUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """댓글 수정 (본인만)"""
    user = await require_current_user(request, db)

    result = await db.execute(
        select(Comment).where(Comment.id == comment_id, Comment.contract_id == contract_id)
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다")

    if comment.user_id != user.id:
        raise HTTPException(status_code=403, detail="본인의 댓글만 수정할 수 있습니다")

    comment.content = data.content.strip()
    comment.updated_at = utc_now()
    await db.commit()

    return {"message": "댓글이 수정되었습니다", "id": comment.id, "content": comment.content}


@router.delete("/{contract_id}/comments/{comment_id}")
async def delete_comment(
    contract_id: int,
    comment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """댓글 삭제 (본인 또는 owner/admin)"""
    user = await require_current_user(request, db)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    result = await db.execute(
        select(Comment).where(Comment.id == comment_id, Comment.contract_id == contract_id)
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다")

    # 본인 댓글이거나, 팀 owner/admin 이면 삭제 가능
    if comment.user_id != user.id:
        if contract.team_id:
            member_result = await db.execute(
                select(TeamMember).where(
                    TeamMember.team_id == contract.team_id,
                    TeamMember.user_id == user.id,
                )
            )
            member = member_result.scalar_one_or_none()
            if not member or "comment.delete_any" not in TEAM_PERMISSIONS.get(member.role, set()):
                raise HTTPException(status_code=403, detail="삭제 권한이 없습니다")
        else:
            raise HTTPException(status_code=403, detail="본인의 댓글만 삭제할 수 있습니다")

    await db.delete(comment)
    await db.commit()

    return {"message": "댓글이 삭제되었습니다"}
