"""발주처 API — Phase 0 (6개 엔드포인트)"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query, UploadFile, File
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


# ── OCR 사업자등록증 자동 인식 ──

ALLOWED_OCR_TYPES = {
    "image/jpeg", "image/png", "image/webp", "application/pdf",
}
MAX_OCR_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/ocr")
@limiter.limit("10/minute")
async def ocr_business_registration(
    request: Request,
    file: UploadFile = File(..., description="사업자등록증 파일 (PDF/JPG/PNG/WebP)"),
    db: AsyncSession = Depends(get_db),
):
    """사업자등록증 OCR — Gemini Vision API로 사업자 정보 추출"""
    user = await require_current_user(request, db)  # noqa: F841

    content_type = file.content_type or ""
    if content_type not in ALLOWED_OCR_TYPES:
        raise HTTPException(
            status_code=400,
            detail="지원하지 않는 파일 형식입니다. PDF, JPG, PNG, WebP만 가능합니다.",
        )

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(file_bytes) > MAX_OCR_SIZE:
        raise HTTPException(status_code=400, detail="파일 크기가 10MB를 초과합니다.")

    # magic bytes 검증
    MAGIC = {
        b'\xff\xd8\xff': "image/jpeg",
        b'\x89PNG': "image/png",
        b'RIFF': "image/webp",
        b'%PDF': "application/pdf",
    }
    detected = None
    for magic, mime in MAGIC.items():
        if file_bytes[:len(magic)] == magic:
            detected = mime
            break
    if detected and detected != content_type:
        logger.warning(f"MIME 불일치: content_type={content_type}, detected={detected}")

    try:
        from app.services.ocr_service import get_ocr_service
        ocr_service = get_ocr_service()
        result = await ocr_service.extract_business_info(file_bytes, detected or content_type)
    except RuntimeError as e:
        logger.error(f"OCR 서비스 초기화 실패: {e}")
        raise HTTPException(status_code=500, detail="OCR 서비스를 사용할 수 없습니다.")
    except Exception as e:
        logger.error(f"OCR 처리 중 오류: {e}")
        raise HTTPException(status_code=500, detail="OCR 처리 중 오류가 발생했습니다.")

    if result is None:
        raise HTTPException(
            status_code=422,
            detail="사업자등록증에서 정보를 추출할 수 없습니다. 이미지를 확인해 주세요.",
        )

    return {"data": result}


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
