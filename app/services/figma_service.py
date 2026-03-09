"""Figma 연동 서비스 — 3차 개발 S3-1 ~ S3-5

Figma API를 통한 파일 메타데이터/스크린샷 조회 + 변경 감지
"""
import logging
import re

import httpx

from app.config import settings
from app.database import async_session, Project, Notification
from sqlalchemy import select

logger = logging.getLogger(__name__)

FIGMA_API_BASE = "https://api.figma.com/v1"

# URL에서 fileKey 추출
_FIGMA_URL_RE = re.compile(
    r"figma\.com/(?:design|file)/([A-Za-z0-9]+)"
)


def parse_figma_file_key(url: str) -> str | None:
    """Figma URL에서 fileKey 추출"""
    m = _FIGMA_URL_RE.search(url)
    return m.group(1) if m else None


def _get_headers() -> dict:
    """Figma API 인증 헤더"""
    token = getattr(settings, "figma_access_token", "")
    if not token:
        return {}
    return {"X-Figma-Token": token}


async def get_figma_file_metadata(file_key: str) -> dict | None:
    """Figma 파일 메타데이터 조회 (GET /v1/files/:key)"""
    headers = _get_headers()
    if not headers:
        logger.warning("FIGMA_ACCESS_TOKEN이 설정되지 않음")
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{FIGMA_API_BASE}/files/{file_key}?depth=1",
                headers=headers,
            )
            if resp.status_code != 200:
                logger.warning(f"Figma API 오류: {resp.status_code} - {resp.text[:200]}")
                return None
            data = resp.json()
            return {
                "name": data.get("name"),
                "last_modified": data.get("lastModified"),
                "thumbnail_url": data.get("thumbnailUrl"),
                "version": data.get("version"),
                "pages": [
                    {"id": p["id"], "name": p["name"]}
                    for p in data.get("document", {}).get("children", [])
                    if p.get("type") == "CANVAS"
                ],
            }
    except Exception as e:
        logger.error(f"Figma API 호출 실패: {e}")
        return None


async def get_figma_images(file_key: str, node_ids: list[str]) -> dict:
    """Figma 노드 이미지(스크린샷) URL 조회"""
    headers = _get_headers()
    if not headers:
        return {}

    try:
        ids_str = ",".join(node_ids)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{FIGMA_API_BASE}/images/{file_key}?ids={ids_str}&format=png&scale=1",
                headers=headers,
            )
            if resp.status_code != 200:
                return {}
            return resp.json().get("images", {})
    except Exception as e:
        logger.error(f"Figma 이미지 조회 실패: {e}")
        return {}


async def validate_figma_url(url: str) -> dict | None:
    """Figma URL 유효성 검증 — 파일 접근 가능 여부 확인 후 메타데이터 반환"""
    file_key = parse_figma_file_key(url)
    if not file_key:
        return None
    return await get_figma_file_metadata(file_key)


async def get_project_figma_files(project) -> list[dict]:
    """프로젝트에 연결된 Figma 파일 정보 조회"""
    urls = project.figma_urls or []
    files = []

    for url in urls:
        file_key = parse_figma_file_key(url)
        if not file_key:
            files.append({"url": url, "error": "유효하지 않은 URL"})
            continue

        meta = await get_figma_file_metadata(file_key)
        if meta:
            files.append({
                "file_key": file_key,
                "url": url,
                "name": meta["name"],
                "thumbnail": meta.get("thumbnail_url"),
                "last_modified": meta.get("last_modified"),
                "pages": meta.get("pages", []),
            })
        else:
            files.append({
                "file_key": file_key,
                "url": url,
                "name": None,
                "error": "접근 불가 (토큰 미설정 또는 권한 없음)",
            })
    return files


# ══════════════════════════════════════════
#  Figma 변경 감지 스케줄러 (S3-5)
# ══════════════════════════════════════════

# 마지막 확인 시점 캐시 (file_key → lastModified)
_last_modified_cache: dict[str, str] = {}


async def check_figma_updates():
    """모든 프로젝트의 Figma 파일 변경 감지 → 팀 알림 발송

    1시간 간격으로 scheduler_service에서 호출
    """
    headers = _get_headers()
    if not headers:
        return

    async with async_session() as db:
        try:
            # figma_urls가 있는 활성 프로젝트 조회
            result = await db.execute(
                select(Project).where(
                    Project.figma_urls.isnot(None),
                    Project.status.in_(["active", "planning"]),
                )
            )
            projects = result.scalars().all()

            for project in projects:
                urls = project.figma_urls or []
                for url in urls:
                    file_key = parse_figma_file_key(url)
                    if not file_key:
                        continue

                    meta = await get_figma_file_metadata(file_key)
                    if not meta:
                        continue

                    last_modified = meta.get("last_modified", "")
                    cached = _last_modified_cache.get(file_key)

                    if cached and cached != last_modified:
                        # 변경 감지 → 팀 멤버에게 알림
                        await _notify_figma_update(db, project, meta.get("name", "Figma 파일"))

                    _last_modified_cache[file_key] = last_modified

            await db.commit()
        except Exception as e:
            logger.error(f"Figma 변경 감지 실패: {e}")
            await db.rollback()


async def _notify_figma_update(db, project, file_name: str):
    """Figma 변경 시 팀 멤버에게 알림 발송"""
    from app.database import TeamMember

    if not project.team_id:
        return

    result = await db.execute(
        select(TeamMember.user_id).where(TeamMember.team_id == project.team_id)
    )
    member_ids = [r[0] for r in result.all()]

    for uid in member_ids:
        db.add(Notification(
            user_id=uid,
            type="figma_update",
            title=f"[{project.project_name}] Figma 시안이 업데이트되었습니다",
            message=f"'{file_name}' 파일이 수정되었습니다.",
            link=f"#/projects/{project.id}?tab=figma",
        ))
