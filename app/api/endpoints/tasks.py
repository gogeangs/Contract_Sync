"""업무 API — Phase 0 (13개 엔드포인트)"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.schemas.task import (
    TaskCreate, TaskUpdate, TaskStatusUpdate, TaskAssigneeUpdate,
    TaskNoteUpdate, TaskMoveRequest, TaskReorderRequest,
    TaskResponse, TaskListResponse, TaskAttachmentResponse,
)
from app.services import task_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=TaskResponse)
@limiter.limit("30/minute")
async def create_task(
    data: TaskCreate,
    request: Request,
    team_id: Optional[int] = Query(None, description="팀 ID"),
    db: AsyncSession = Depends(get_db),
):
    """업무 생성"""
    user = await require_current_user(request, db)
    try:
        task = await task_service.create(db, user, data, team_id)
        return await task_service.enrich_one(db, task)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"업무 생성 실패: {e}")
        raise HTTPException(status_code=500, detail="업무 생성에 실패했습니다")


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    request: Request,
    project_id: Optional[int] = Query(None, description="프로젝트 필터"),
    status: Optional[str] = Query(None, description="상태 필터"),
    assignee_id: Optional[int] = Query(None, description="담당자 필터"),
    priority: Optional[str] = Query(None, description="우선순위 필터"),
    search: Optional[str] = Query(None, description="검색어"),
    team_id: Optional[int] = Query(None, description="팀 ID 필터"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """업무 목록"""
    user = await require_current_user(request, db)
    rows, total = await task_service.get_list(
        db, user, project_id=project_id, status=status,
        assignee_id=assignee_id, priority=priority, search=search,
        team_id=team_id, page=page, size=size,
    )
    enriched = await task_service.enrich_list(db, rows)
    return {"tasks": enriched, "total": total}


@router.patch("/reorder")
@limiter.limit("10/minute")
async def reorder_tasks(
    data: TaskReorderRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """업무 순서 변경 (벌크)"""
    user = await require_current_user(request, db)
    try:
        await task_service.reorder(db, user, data.task_orders)
        return {"message": "순서가 변경되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"순서 변경 실패: {e}")
        raise HTTPException(status_code=500, detail="순서 변경에 실패했습니다")


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """업무 상세"""
    user = await require_current_user(request, db)
    task = await task_service.get_detail(db, user, task_id)
    return await task_service.enrich_one(db, task)


@router.put("/{task_id}", response_model=TaskResponse)
@limiter.limit("30/minute")
async def update_task(
    task_id: int,
    data: TaskUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """업무 수정"""
    user = await require_current_user(request, db)
    try:
        task = await task_service.update(db, user, task_id, data)
        return await task_service.enrich_one(db, task)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"업무 수정 실패: {e}")
        raise HTTPException(status_code=500, detail="업무 수정에 실패했습니다")


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """업무 삭제"""
    user = await require_current_user(request, db)
    try:
        await task_service.delete(db, user, task_id)
        return {"message": "업무가 삭제되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"업무 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail="업무 삭제에 실패했습니다")


@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: int,
    data: TaskStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """업무 상태 변경"""
    user = await require_current_user(request, db)
    try:
        task = await task_service.update_status(db, user, task_id, data.status)
        return await task_service.enrich_one(db, task)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"상태 변경 실패: {e}")
        raise HTTPException(status_code=500, detail="상태 변경에 실패했습니다")


@router.patch("/{task_id}/assignee", response_model=TaskResponse)
async def update_task_assignee(
    task_id: int,
    data: TaskAssigneeUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """담당자 변경"""
    user = await require_current_user(request, db)
    try:
        task = await task_service.update_assignee(db, user, task_id, data.assignee_id)
        return await task_service.enrich_one(db, task)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"담당자 변경 실패: {e}")
        raise HTTPException(status_code=500, detail="담당자 변경에 실패했습니다")


@router.patch("/{task_id}/note", response_model=TaskResponse)
async def update_task_note(
    task_id: int,
    data: TaskNoteUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """처리 내용 저장"""
    user = await require_current_user(request, db)
    try:
        task = await task_service.update_note(db, user, task_id, data.note)
        return await task_service.enrich_one(db, task)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"노트 저장 실패: {e}")
        raise HTTPException(status_code=500, detail="처리 내용 저장에 실패했습니다")


@router.patch("/{task_id}/move", response_model=TaskResponse)
@limiter.limit("20/minute")
async def move_task(
    task_id: int,
    data: TaskMoveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 이동"""
    user = await require_current_user(request, db)
    try:
        task = await task_service.move_task(db, user, task_id, data.project_id)
        return await task_service.enrich_one(db, task)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"업무 이동 실패: {e}")
        raise HTTPException(status_code=500, detail="업무 이동에 실패했습니다")


@router.post("/{task_id}/attachments", response_model=TaskAttachmentResponse)
@limiter.limit("20/minute")
async def upload_attachment(
    task_id: int,
    file: UploadFile = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """산출물 업로드"""
    user = await require_current_user(request, db)

    # 스트리밍으로 파일 읽기 (메모리 고갈 방지)
    chunks = []
    total = 0
    while chunk := await file.read(8192):
        total += len(chunk)
        if total > task_service.MAX_FILE_SIZE:
            chunks.clear()
            raise HTTPException(status_code=400, detail="파일 크기는 20MB를 초과할 수 없습니다")
        chunks.append(chunk)
    content = b"".join(chunks)

    try:
        att = await task_service.upload_attachment(
            db, user, task_id,
            file_name=file.filename or "unknown",
            file_content=content,
            mime_type=file.content_type or "application/octet-stream",
        )
        return TaskAttachmentResponse(
            id=att.id, task_id=att.task_id, file_name=att.file_name,
            file_size=att.file_size, mime_type=att.mime_type,
            uploaded_by=att.uploaded_by,
            uploader_name=user.name or user.email,
            created_at=att.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"산출물 업로드 실패: {e}")
        raise HTTPException(status_code=500, detail="산출물 업로드에 실패했습니다")


@router.delete("/{task_id}/attachments/{attachment_id}")
async def delete_attachment(
    task_id: int,
    attachment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """산출물 삭제"""
    user = await require_current_user(request, db)
    try:
        await task_service.delete_attachment(db, user, task_id, attachment_id)
        return {"message": "산출물이 삭제되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"산출물 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail="산출물 삭제에 실패했습니다")


@router.get("/{task_id}/attachments/{attachment_id}")
async def download_attachment(
    task_id: int,
    attachment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """산출물 다운로드"""
    user = await require_current_user(request, db)
    att, path = await task_service.get_attachment(db, user, task_id, attachment_id)
    return FileResponse(path, filename=att.file_name)
