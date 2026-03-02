"""템플릿 + 반복 업무 엔드포인트 — Phase 5 (8개)"""
import logging

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.schemas.template import (
    TemplateCreate, TemplateUpdate, TemplateResponse, TemplateListResponse,
    RecurringTaskCreate, RecurringTaskUpdate, RecurringTaskResponse,
)
from app.services import template_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ══════════════════════════════════════════
# 프로젝트 템플릿 (§14) — 5개
# ══════════════════════════════════════════

@router.post("/templates", response_model=TemplateResponse)
@limiter.limit("10/minute")
async def create_template(
    data: TemplateCreate,
    request: Request,
    team_id: Optional[int] = Query(None, description="팀 ID"),
    db: AsyncSession = Depends(get_db),
):
    """템플릿 저장"""
    user = await require_current_user(request, db)
    try:
        template = await template_service.create_template(db, user, data, team_id)
        return await template_service.enrich_template(db, template)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"템플릿 저장 실패: {e}")
        raise HTTPException(status_code=500, detail="템플릿 저장에 실패했습니다")


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """템플릿 목록"""
    user = await require_current_user(request, db)
    try:
        templates, total = await template_service.list_templates(db, user)
        enriched = [await template_service.enrich_template(db, t) for t in templates]
        return {"templates": enriched, "total": total}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"템플릿 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="템플릿 목록 조회에 실패했습니다")


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """템플릿 상세"""
    user = await require_current_user(request, db)
    try:
        template = await template_service.get_template(db, user, template_id)
        return await template_service.enrich_template(db, template)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"템플릿 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="템플릿 조회에 실패했습니다")


@router.put("/templates/{template_id}", response_model=TemplateResponse)
@limiter.limit("10/minute")
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """템플릿 수정"""
    user = await require_current_user(request, db)
    try:
        template = await template_service.update_template(db, user, template_id, data)
        return await template_service.enrich_template(db, template)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"템플릿 수정 실패: {e}")
        raise HTTPException(status_code=500, detail="템플릿 수정에 실패했습니다")


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """템플릿 삭제"""
    user = await require_current_user(request, db)
    try:
        await template_service.delete_template(db, user, template_id)
        return {"message": "템플릿이 삭제되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"템플릿 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail="템플릿 삭제에 실패했습니다")


# ══════════════════════════════════════════
# 반복 업무 (§15) — 3개
# ══════════════════════════════════════════

@router.post("/projects/{project_id}/recurring-tasks", response_model=RecurringTaskResponse)
@limiter.limit("10/minute")
async def create_recurring_task(
    project_id: int,
    data: RecurringTaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """반복 업무 설정"""
    user = await require_current_user(request, db)
    try:
        task = await template_service.create_recurring_task(db, user, project_id, data)
        return await template_service.enrich_recurring_task(db, task)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"반복 업무 설정 실패: {e}")
        raise HTTPException(status_code=500, detail="반복 업무 설정에 실패했습니다")


@router.get("/projects/{project_id}/recurring-tasks", response_model=list[RecurringTaskResponse])
async def list_recurring_tasks(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """반복 업무 목록"""
    user = await require_current_user(request, db)
    try:
        tasks = await template_service.list_recurring_tasks(db, user, project_id)
        return [await template_service.enrich_recurring_task(db, t) for t in tasks]
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"반복 업무 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="반복 업무 목록 조회에 실패했습니다")


@router.patch("/recurring-tasks/{task_id}", response_model=RecurringTaskResponse)
@limiter.limit("10/minute")
async def update_recurring_task(
    task_id: int,
    data: RecurringTaskUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """반복 업무 수정/비활성화"""
    user = await require_current_user(request, db)
    try:
        task = await template_service.update_recurring_task(db, user, task_id, data)
        return await template_service.enrich_recurring_task(db, task)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"반복 업무 수정 실패: {e}")
        raise HTTPException(status_code=500, detail="반복 업무 수정에 실패했습니다")


@router.delete("/recurring-tasks/{task_id}")
async def delete_recurring_task(
    task_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """반복 업무 삭제"""
    user = await require_current_user(request, db)
    try:
        await template_service.delete_recurring_task(db, user, task_id)
        return {"message": "반복 업무가 삭제되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"반복 업무 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail="반복 업무 삭제에 실패했습니다")
