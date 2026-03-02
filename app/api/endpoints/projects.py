"""프로젝트 API — Phase 0 (7개 엔드포인트)"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectStatusUpdate,
    ProjectResponse, ProjectListResponse,
)
from app.services import project_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ProjectResponse)
@limiter.limit("30/minute")
async def create_project(
    data: ProjectCreate,
    request: Request,
    team_id: Optional[int] = Query(None, description="팀 ID"),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 생성"""
    user = await require_current_user(request, db)
    try:
        project = await project_service.create(db, user, data, team_id)
        return await project_service.enrich_one(db, project)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"프로젝트 생성 실패: {e}")
        raise HTTPException(status_code=500, detail="프로젝트 생성에 실패했습니다")


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    request: Request,
    status: Optional[str] = Query(None, description="상태 필터"),
    project_type: Optional[str] = Query(None, alias="type", description="유형 필터"),
    client_id: Optional[int] = Query(None, description="발주처 필터"),
    search: Optional[str] = Query(None, description="검색어"),
    team_id: Optional[int] = Query(None, description="팀 ID 필터"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 목록"""
    user = await require_current_user(request, db)
    rows, total = await project_service.get_list(
        db, user, status=status, project_type=project_type,
        client_id=client_id, search=search, team_id=team_id,
        page=page, size=size,
    )
    enriched = await project_service.enrich_list(db, rows)
    return {"projects": enriched, "total": total}


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 상세"""
    user = await require_current_user(request, db)
    project = await project_service.get_detail(db, user, project_id)
    return await project_service.enrich_one(db, project)


@router.put("/{project_id}", response_model=ProjectResponse)
@limiter.limit("30/minute")
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 수정"""
    user = await require_current_user(request, db)
    try:
        project = await project_service.update(db, user, project_id, data)
        return await project_service.enrich_one(db, project)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"프로젝트 수정 실패: {e}")
        raise HTTPException(status_code=500, detail="프로젝트 수정에 실패했습니다")


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 삭제"""
    user = await require_current_user(request, db)
    try:
        await project_service.delete(db, user, project_id)
        return {"message": "프로젝트가 삭제되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"프로젝트 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail="프로젝트 삭제에 실패했습니다")


@router.patch("/{project_id}/status", response_model=ProjectResponse)
async def update_project_status(
    project_id: int,
    data: ProjectStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 상태 변경"""
    user = await require_current_user(request, db)
    try:
        project = await project_service.update_status(db, user, project_id, data.status)
        return await project_service.enrich_one(db, project)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"상태 변경 실패: {e}")
        raise HTTPException(status_code=500, detail="상태 변경에 실패했습니다")


@router.post("/from-template/{template_id}", response_model=ProjectResponse)
@limiter.limit("10/minute")
async def create_from_template(
    template_id: int,
    request: Request,
    team_id: Optional[int] = Query(None, description="팀 ID"),
    db: AsyncSession = Depends(get_db),
):
    """템플릿에서 프로젝트 생성"""
    user = await require_current_user(request, db)
    try:
        project = await project_service.create_from_template(db, user, template_id, team_id)
        return await project_service.enrich_one(db, project)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"템플릿 생성 실패: {e}")
        raise HTTPException(status_code=500, detail="템플릿에서 프로젝트 생성에 실패했습니다")
