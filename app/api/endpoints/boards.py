"""4차 개발 Phase 1 — 게시판/공지사항 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc, asc
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.database import (
    get_db, Board, BoardPost, BoardComment,
    TeamMember, User, Notification, ActivityLog, utc_now,
)
from app.api.endpoints.auth import require_current_user
from app.api.endpoints.teams import get_team_member

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Pydantic 모델 ──────────────────────────────

class BoardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern=r'^(notice|free|archive)$')


class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1)
    file_urls: Optional[list] = None


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    content: Optional[str] = Field(None, min_length=1)
    file_urls: Optional[list] = None


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


# ── 헬퍼 ──────────────────────────────────────

async def _require_team_member(db: AsyncSession, team_id: int, user_id: int) -> TeamMember:
    member = await get_team_member(db, team_id, user_id)
    if not member:
        raise HTTPException(status_code=403, detail="팀 멤버가 아닙니다.")
    return member


async def _require_board_access(db: AsyncSession, board: Board, user_id: int) -> Optional[TeamMember]:
    """게시판 접근 권한 확인 — 개인 게시판이면 소유자 확인, 팀이면 멤버 확인"""
    if board.user_id and not board.team_id:
        if board.user_id != user_id:
            raise HTTPException(status_code=403, detail="본인의 게시판이 아닙니다.")
        return None
    return await _require_team_member(db, board.team_id, user_id)


def _post_to_dict(post: BoardPost, author: User = None) -> dict:
    return {
        "id": post.id,
        "board_id": post.board_id,
        "author_id": post.author_id,
        "author_name": author.name if author else None,
        "author_picture": author.picture if author else None,
        "title": post.title,
        "content": post.content,
        "is_pinned": post.is_pinned,
        "view_count": post.view_count,
        "file_urls": post.file_urls,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
    }


# ── 개인 게시판 ────────────────────────────────

@router.get("/my/boards")
async def list_my_boards(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """개인 게시판 목록"""
    result = await db.execute(
        select(Board).where(Board.user_id == current_user.id, Board.team_id.is_(None)).order_by(Board.created_at)
    )
    boards = result.scalars().all()

    # 기본 게시판 자동 생성
    if not boards:
        defaults = [
            Board(user_id=current_user.id, name="메모", type="free"),
            Board(user_id=current_user.id, name="자료실", type="archive"),
        ]
        for b in defaults:
            db.add(b)
        await db.commit()
        for b in defaults:
            await db.refresh(b)
        boards = defaults

    items = []
    for b in boards:
        cnt = await db.execute(
            select(func.count(BoardPost.id)).where(BoardPost.board_id == b.id)
        )
        items.append({
            "id": b.id,
            "team_id": None,
            "user_id": b.user_id,
            "name": b.name,
            "type": b.type,
            "post_count": cnt.scalar() or 0,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })
    return items


# ── 팀 게시판 CRUD ────────────────────────────────

@router.get("/teams/{team_id}/boards")
async def list_boards(
    team_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """게시판 목록"""
    await _require_team_member(db, team_id, current_user.id)

    result = await db.execute(
        select(Board).where(Board.team_id == team_id).order_by(Board.created_at)
    )
    boards = result.scalars().all()

    # 게시판이 없으면 기본 3개 자동 생성
    if not boards:
        defaults = [
            Board(team_id=team_id, name="공지사항", type="notice"),
            Board(team_id=team_id, name="자유게시판", type="free"),
            Board(team_id=team_id, name="자료실", type="archive"),
        ]
        for b in defaults:
            db.add(b)
        await db.commit()
        for b in defaults:
            await db.refresh(b)
        boards = defaults

    items = []
    for b in boards:
        # 게시글 수 조회
        cnt = await db.execute(
            select(func.count(BoardPost.id)).where(BoardPost.board_id == b.id)
        )
        items.append({
            "id": b.id,
            "team_id": b.team_id,
            "name": b.name,
            "type": b.type,
            "post_count": cnt.scalar() or 0,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })
    return items


@router.post("/teams/{team_id}/boards")
async def create_board(
    team_id: int,
    body: BoardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """게시판 생성 (owner/admin)"""
    member = await _require_team_member(db, team_id, current_user.id)
    if member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="게시판 생성 권한이 없습니다.")

    board = Board(team_id=team_id, name=body.name, type=body.type)
    db.add(board)
    await db.commit()
    await db.refresh(board)
    return {"id": board.id, "name": board.name, "type": board.type}


# ── 게시글 CRUD ────────────────────────────────

@router.get("/boards/{board_id}/posts")
async def list_posts(
    board_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """게시글 목록 (페이지네이션 + 검색)"""
    board = await db.get(Board, board_id)
    if not board:
        raise HTTPException(status_code=404, detail="게시판을 찾을 수 없습니다.")
    # 개인 게시판: 소유자 확인 / 팀 게시판: 멤버 확인
    if board.user_id and not board.team_id:
        if board.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="본인의 게시판이 아닙니다.")
    else:
        await _require_team_member(db, board.team_id, current_user.id)

    query = select(BoardPost, User).join(User, BoardPost.author_id == User.id).where(
        BoardPost.board_id == board_id
    )
    count_query = select(func.count(BoardPost.id)).where(BoardPost.board_id == board_id)

    if search:
        search_filter = or_(
            BoardPost.title.ilike(f"%{search}%"),
            BoardPost.content.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # 고정글 우선, 최신순
    query = query.order_by(desc(BoardPost.is_pinned), desc(BoardPost.created_at))
    query = query.offset((page - 1) * size).limit(size)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query)
    rows = result.all()

    # 댓글 수 조회
    post_ids = [r[0].id for r in rows]
    comment_counts = {}
    if post_ids:
        cc_result = await db.execute(
            select(BoardComment.post_id, func.count(BoardComment.id))
            .where(BoardComment.post_id.in_(post_ids))
            .group_by(BoardComment.post_id)
        )
        comment_counts = dict(cc_result.all())

    items = []
    for post, author in rows:
        d = _post_to_dict(post, author)
        d["comment_count"] = comment_counts.get(post.id, 0)
        items.append(d)

    return {"items": items, "total": total, "page": page, "size": size}


@router.post("/boards/{board_id}/posts")
async def create_post(
    board_id: int,
    body: PostCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """게시글 작성"""
    board = await db.get(Board, board_id)
    if not board:
        raise HTTPException(status_code=404, detail="게시판을 찾을 수 없습니다.")

    # 개인 게시판: 소유자 확인
    if board.user_id and not board.team_id:
        if board.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="본인의 게시판이 아닙니다.")
        member = None
    else:
        member = await _require_team_member(db, board.team_id, current_user.id)

    # 공지사항은 owner/admin만
    if board.type == "notice" and member and member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="공지사항은 관리자만 작성할 수 있습니다.")

    post = BoardPost(
        board_id=board_id,
        author_id=current_user.id,
        title=body.title,
        content=body.content,
        file_urls=body.file_urls,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    # 활동 로그
    db.add(ActivityLog(
        team_id=board.team_id,
        user_id=current_user.id,
        action="create",
        target_type="board_post",
        target_name=body.title,
        detail=f"게시판: {board.name}",
    ))
    await db.commit()

    return _post_to_dict(post, current_user)


@router.get("/posts/{post_id}")
async def get_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """게시글 상세 (조회수 증가)"""
    result = await db.execute(
        select(BoardPost, User).join(User, BoardPost.author_id == User.id)
        .where(BoardPost.id == post_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    post, author = row

    board = await db.get(Board, post.board_id)
    await _require_board_access(db, board, current_user.id)

    # 조회수 증가
    post.view_count = (post.view_count or 0) + 1
    await db.commit()

    # 댓글 조회
    comments_result = await db.execute(
        select(BoardComment, User)
        .join(User, BoardComment.author_id == User.id)
        .where(BoardComment.post_id == post_id)
        .order_by(asc(BoardComment.created_at))
    )
    comments = [
        {
            "id": c.id,
            "author_id": c.author_id,
            "author_name": u.name,
            "author_picture": u.picture,
            "content": c.content,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c, u in comments_result.all()
    ]

    d = _post_to_dict(post, author)
    d["comments"] = comments
    d["board_name"] = board.name
    d["board_type"] = board.type
    d["team_id"] = board.team_id
    return d


@router.put("/posts/{post_id}")
async def update_post(
    post_id: int,
    body: PostUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """게시글 수정 (본인 또는 owner/admin)"""
    post = await db.get(BoardPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    board = await db.get(Board, post.board_id)
    member = await _require_team_member(db, board.team_id, current_user.id)

    if post.author_id != current_user.id and member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="수정 권한이 없습니다.")

    if body.title is not None:
        post.title = body.title
    if body.content is not None:
        post.content = body.content
    if body.file_urls is not None:
        post.file_urls = body.file_urls
    post.updated_at = utc_now()
    await db.commit()
    await db.refresh(post)

    author = await db.get(User, post.author_id)
    return _post_to_dict(post, author)


@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """게시글 삭제 (본인 또는 owner/admin)"""
    post = await db.get(BoardPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    board = await db.get(Board, post.board_id)
    member = await _require_board_access(db, board, current_user.id)

    if post.author_id != current_user.id and member and member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다.")

    await db.delete(post)
    await db.commit()
    return {"ok": True}


@router.patch("/posts/{post_id}/pin")
async def toggle_pin(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """공지 고정/해제 (owner/admin 또는 개인 게시판 소유자)"""
    post = await db.get(BoardPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    board = await db.get(Board, post.board_id)
    member = await _require_board_access(db, board, current_user.id)

    if member and member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="고정 권한이 없습니다.")

    post.is_pinned = not post.is_pinned
    await db.commit()
    return {"id": post.id, "is_pinned": post.is_pinned}


# ── 댓글 CRUD ──────────────────────────────────

@router.post("/posts/{post_id}/comments")
async def create_comment(
    post_id: int,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """댓글 작성"""
    post = await db.get(BoardPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    board = await db.get(Board, post.board_id)
    await _require_board_access(db, board, current_user.id)

    comment = BoardComment(
        post_id=post_id,
        author_id=current_user.id,
        content=body.content,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # 글 작성자에게 알림 (본인이 아닌 경우)
    if post.author_id != current_user.id:
        db.add(Notification(
            user_id=post.author_id,
            type="board_comment",
            title=f"'{post.title}'에 새 댓글",
            message=f"{current_user.name}님이 댓글을 남겼습니다.",
            link=f"#/boards/post/{post_id}",
        ))
        await db.commit()

    return {
        "id": comment.id,
        "post_id": post_id,
        "author_id": current_user.id,
        "author_name": current_user.name,
        "content": comment.content,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """댓글 삭제 (본인 또는 owner/admin)"""
    comment = await db.get(BoardComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다.")

    post = await db.get(BoardPost, comment.post_id)
    board = await db.get(Board, post.board_id)
    member = await _require_board_access(db, board, current_user.id)

    if comment.author_id != current_user.id and member and member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다.")

    await db.delete(comment)
    await db.commit()
    return {"ok": True}
