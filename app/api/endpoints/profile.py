"""4차 개발 Phase 1 — 프로필 이미지 업로드 API"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import logging

from app.database import get_db, User
from app.api.endpoints.auth import require_current_user
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_SIZE = 2 * 1024 * 1024  # 2MB


def _get_upload_dir() -> Path:
    if settings.data_dir:
        base = Path(settings.data_dir) / "uploads" / "profiles"
    else:
        base = Path(__file__).resolve().parent.parent.parent.parent / "uploads" / "profiles"
    base.mkdir(parents=True, exist_ok=True)
    return base


@router.post("/auth/profile/picture")
async def upload_profile_picture(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """프로필 이미지 업로드"""
    # 확장자 검증
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 이미지 형식입니다. ({', '.join(ALLOWED_EXTENSIONS)})"
        )

    # 파일 크기 검증
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="이미지 크기는 2MB 이하여야 합니다.")

    # 기존 프로필 이미지 삭제
    upload_dir = _get_upload_dir()
    for old_file in upload_dir.glob(f"{current_user.id}.*"):
        old_file.unlink(missing_ok=True)

    # 저장
    filename = f"{current_user.id}{ext}"
    filepath = upload_dir / filename
    filepath.write_bytes(content)

    # DB 업데이트 — /uploads/ 경로는 main.py에서 StaticFiles로 서빙
    picture_url = f"/uploads/profiles/{filename}"

    current_user.picture = picture_url
    await db.commit()

    logger.info(f"프로필 이미지 업로드: user={current_user.id}, file={filename}")
    return {"picture": picture_url}


@router.delete("/auth/profile/picture")
async def delete_profile_picture(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """프로필 이미지 삭제 (기본으로 복원)"""
    upload_dir = _get_upload_dir()
    for old_file in upload_dir.glob(f"{current_user.id}.*"):
        old_file.unlink(missing_ok=True)

    current_user.picture = None
    await db.commit()

    return {"ok": True, "picture": None}
