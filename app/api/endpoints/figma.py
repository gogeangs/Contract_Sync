"""Figma 연동 API — 3차 개발 S3-1 ~ S3-2

GET /projects/{id}/figma — 연결된 Figma 파일 조회
POST /projects/{id}/figma — Figma URL 등록
DELETE /projects/{id}/figma — Figma URL 삭제
GET /projects/{id}/figma/screenshots — 페이지 스크린샷
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.auth import require_current_user
from app.database import Project, get_db
from app.limiter import limiter
from app.services.common import get_user_team_ids, access_filter, log_activity
from app.services.figma_service import (
    get_project_figma_files,
    validate_figma_url,
    parse_figma_file_key,
    get_figma_images,
)
from sqlalchemy import select

router = APIRouter()


class FigmaUrlRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=500)


class FigmaUrlDeleteRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=500)


class FigmaScreenshotRequest(BaseModel):
    file_key: str = Field(..., min_length=1)
    node_ids: list[str] = Field(..., min_length=1, max_length=20)


async def _get_project(db: AsyncSession, project_id: int, user_id: int) -> Project:
    """프로젝트 접근 권한 확인 후 반환"""
    team_ids = await get_user_team_ids(db, user_id)
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            access_filter(Project, user_id, team_ids),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return project


@router.get("/projects/{project_id}/figma")
@limiter.limit("30/minute")
async def list_figma_files(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """프로젝트에 연결된 Figma 파일 목록 조회"""
    user = await require_current_user(request, db)
    project = await _get_project(db, project_id, user.id)
    files = await get_project_figma_files(project)
    return {"files": files, "urls": project.figma_urls or []}


@router.post("/projects/{project_id}/figma")
@limiter.limit("10/minute")
async def add_figma_url(
    project_id: int,
    data: FigmaUrlRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Figma URL 등록"""
    user = await require_current_user(request, db)
    project = await _get_project(db, project_id, user.id)

    # URL 형식 검증
    file_key = parse_figma_file_key(data.url)
    if not file_key:
        raise HTTPException(status_code=400, detail="유효하지 않은 Figma URL입니다.")

    # 중복 확인
    existing = project.figma_urls or []
    if data.url in existing:
        raise HTTPException(status_code=400, detail="이미 등록된 URL입니다.")

    # Figma API로 접근 가능 여부 확인 (토큰이 설정된 경우)
    meta = await validate_figma_url(data.url)

    existing.append(data.url)
    project.figma_urls = existing
    await db.commit()

    await log_activity(
        db, user.id, "create", "figma",
        meta.get("name", data.url) if meta else data.url,
        project_id=project_id, team_id=project.team_id,
    )

    return {
        "message": "Figma 파일이 연결되었습니다.",
        "url": data.url,
        "metadata": meta,
    }


@router.delete("/projects/{project_id}/figma")
@limiter.limit("10/minute")
async def remove_figma_url(
    project_id: int,
    data: FigmaUrlDeleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Figma URL 삭제"""
    user = await require_current_user(request, db)
    project = await _get_project(db, project_id, user.id)

    existing = project.figma_urls or []
    if data.url not in existing:
        raise HTTPException(status_code=404, detail="해당 URL이 등록되어 있지 않습니다.")

    existing.remove(data.url)
    project.figma_urls = existing if existing else None
    await db.commit()

    return {"message": "Figma 파일 연결이 해제되었습니다."}


@router.post("/projects/{project_id}/figma/screenshots")
@limiter.limit("10/minute")
async def get_screenshots(
    project_id: int,
    data: FigmaScreenshotRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Figma 노드 스크린샷 조회"""
    user = await require_current_user(request, db)
    await _get_project(db, project_id, user.id)

    images = await get_figma_images(data.file_key, data.node_ids)
    return {"images": images}
