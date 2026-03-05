from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional
import re
import json
import logging

from app.database import (
    get_db, User, Comment, Project, Task, TeamMember,
    Notification, ActivityLog, TEAM_PERMISSIONS, utc_now,
)
from app.api.endpoints.auth import require_current_user
from app.services.common import get_user_team_ids, get_accessible

logger = logging.getLogger(__name__)

router = APIRouter()


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    task_id: Optional[int] = None


class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


def _extract_mentions(content: str) -> list[str]:
    """@[이름](email) 또는 @email 형식의 멘션에서 이메일 추출 (최대 10명)"""
    # 새 형식: @[표시이름](email) — 대괄호 중첩 방지
    new_format = re.findall(r'@\[[^\[\]]+\]\(([\w.+-]+@[\w-]+\.[\w.-]+)\)', content)
    # 기존 형식: @email (하위 호환)
    legacy = re.findall(r'(?<!\()@([\w.+-]+@[\w-]+\.[\w.-]+)', content)
    combined = list(dict.fromkeys(new_format + legacy))  # 중복 제거, 순서 유지
    return combined[:10]


async def _notify_mentions(db: AsyncSession, mentions: list[str], comment: Comment, user: User, project: Project):
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
            link=json.dumps({"project_id": project.id, "task_id": comment.task_id}),
        )
        db.add(notif)


@router.get("/{project_id}/comments")
async def list_comments(
    project_id: int,
    task_id: Optional[int] = Query(None),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """프로젝트/업무 댓글 목록 조회"""
    user = await require_current_user(request, db)
    team_ids = await get_user_team_ids(db, user.id)

    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    query = select(Comment, User).join(User, User.id == Comment.user_id).where(
        Comment.project_id == project_id
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
            "project_id": c.project_id,
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


@router.post("/{project_id}/comments")
async def create_comment(
    project_id: int,
    data: CommentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """댓글 작성"""
    user = await require_current_user(request, db)
    team_ids = await get_user_team_ids(db, user.id)

    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    if not data.content or not data.content.strip():
        raise HTTPException(status_code=400, detail="댓글 내용을 입력해주세요.")

    # M-2: 댓글 길이 제한
    if len(data.content) > 5000:
        raise HTTPException(status_code=400, detail="댓글은 5000자를 초과할 수 없습니다.")

    comment = Comment(
        project_id=project_id,
        task_id=data.task_id,
        user_id=user.id,
        content=data.content.strip(),
    )
    db.add(comment)

    # 활동 로그 — v2: Task 테이블에서 이름 조회
    task_name = ""
    if data.task_id:
        task_result = await db.execute(
            select(Task.task_name).where(Task.id == data.task_id)
        )
        task_name = task_result.scalar_one_or_none() or ""

    log = ActivityLog(
        project_id=project_id,
        team_id=project.team_id,
        user_id=user.id,
        action="comment",
        target_type="task" if data.task_id else "project",
        target_name=task_name or project.project_name,
        detail=data.content[:200],
    )
    db.add(log)

    # @멘션 알림
    mentions = _extract_mentions(data.content)
    await _notify_mentions(db, mentions, comment, user, project)

    # 팀 프로젝트이면 팀 멤버에게 댓글 알림 (본인 제외)
    # M-4: N+1 쿼리 해결 - JOIN으로 한 번에 조회
    if project.team_id:
        members_result = await db.execute(
            select(TeamMember.user_id, User.email)
            .join(User, User.id == TeamMember.user_id)
            .where(
                TeamMember.team_id == project.team_id,
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
                    link=json.dumps({"project_id": project_id, "task_id": data.task_id}),
                )
                db.add(notif)

    await db.commit()
    await db.refresh(comment)

    return {
        "id": comment.id,
        "project_id": comment.project_id,
        "task_id": comment.task_id,
        "content": comment.content,
        "user_id": user.id,
        "user_name": user.name or user.email,
        "user_picture": user.picture,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
        "is_mine": True,
    }


@router.put("/{project_id}/comments/{comment_id}")
async def update_comment(
    project_id: int,
    comment_id: int,
    data: CommentUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """댓글 수정 (본인만)"""
    user = await require_current_user(request, db)

    result = await db.execute(
        select(Comment).where(Comment.id == comment_id, Comment.project_id == project_id)
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


@router.delete("/{project_id}/comments/{comment_id}")
async def delete_comment(
    project_id: int,
    comment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """댓글 삭제 (본인 또는 owner/admin)"""
    user = await require_current_user(request, db)
    team_ids = await get_user_team_ids(db, user.id)

    project = await get_accessible(db, Project, project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    result = await db.execute(
        select(Comment).where(Comment.id == comment_id, Comment.project_id == project_id)
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다")

    # 본인 댓글이거나, 팀 owner/admin 이면 삭제 가능
    if comment.user_id != user.id:
        if project.team_id:
            member_result = await db.execute(
                select(TeamMember).where(
                    TeamMember.team_id == project.team_id,
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
