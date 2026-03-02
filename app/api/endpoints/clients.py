"""발주처 API — Phase 0 (6개 엔드포인트)"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse, ClientListResponse
from app.services import client_service, project_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ClientResponse)
@limiter.limit("20/minute")
async def create_client(
    data: ClientCreate,
    request: Request,
    team_id: Optional[int] = Query(None, description="팀 ID"),
    db: AsyncSession = Depends(get_db),
):
    """발주처 등록"""
    user = await require_current_user(request, db)
    try:
        client = await client_service.create(db, user, data, team_id)
        return await client_service.enrich_one(db, client)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"발주처 등록 실패: {e}")
        raise HTTPException(status_code=500, detail="발주처 등록에 실패했습니다")


@router.get("", response_model=ClientListResponse)
async def list_clients(
    request: Request,
    search: Optional[str] = Query(None, description="검색어"),
    category: Optional[str] = Query(None, description="업종 필터"),
    team_id: Optional[int] = Query(None, description="팀 ID 필터"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """발주처 목록"""
    user = await require_current_user(request, db)
    rows, total = await client_service.get_list(
        db, user, search=search, category=category, team_id=team_id, page=page, size=size,
    )
    enriched = await client_service.enrich_list(db, rows)
    return {"clients": enriched, "total": total}


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """발주처 상세"""
    user = await require_current_user(request, db)
    client = await client_service.get_detail(db, user, client_id)
    return await client_service.enrich_one(db, client)


@router.put("/{client_id}", response_model=ClientResponse)
@limiter.limit("20/minute")
async def update_client(
    client_id: int,
    data: ClientUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """발주처 수정"""
    user = await require_current_user(request, db)
    try:
        client = await client_service.update(db, user, client_id, data)
        return await client_service.enrich_one(db, client)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"발주처 수정 실패: {e}")
        raise HTTPException(status_code=500, detail="발주처 수정에 실패했습니다")


@router.delete("/{client_id}")
async def delete_client(
    client_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """발주처 삭제 (연관 프로젝트 없을 때만)"""
    user = await require_current_user(request, db)
    try:
        await client_service.delete(db, user, client_id)
        return {"message": "발주처가 삭제되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"발주처 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail="발주처 삭제에 실패했습니다")


@router.get("/{client_id}/projects")
async def get_client_projects(
    client_id: int,
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """발주처의 프로젝트 목록"""
    user = await require_current_user(request, db)
    rows, total = await client_service.get_projects(db, user, client_id, page=page, size=size)
    enriched = await project_service.enrich_list(db, rows)
    return {"projects": enriched, "total": total}
