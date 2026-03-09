"""MCP 추천 API — 3차 개발 S7-1, S7-2 (선택)

GET /mcp/recommendations — 내 MCP 추천 조회
POST /mcp/recommendations/generate — MCP 추천 생성 (패턴 분석)
POST /mcp/recommendations/{id}/dismiss — 추천 닫기
GET /mcp/catalog — MCP 카탈로그
"""
from fastapi import APIRouter, Request, Query, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.auth import require_current_user
from app.database import get_db
from app.limiter import limiter
from app.services.mcp_recommendation_service import (
    get_user_recommendations,
    generate_recommendations,
    dismiss_recommendation,
    analyze_team_patterns,
    MCP_CATALOG,
)
from app.services.common import get_user_team_ids

router = APIRouter(prefix="/mcp")


@router.get("/recommendations")
@limiter.limit("30/minute")
async def list_recommendations(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """내 MCP 추천 조회"""
    user = await require_current_user(request, db)
    recs = await get_user_recommendations(db, user.id)
    return {"recommendations": recs}


@router.post("/recommendations/generate")
@limiter.limit("5/minute")
async def generate(
    request: Request,
    team_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """MCP 추천 생성 (업무 패턴 분석)"""
    user = await require_current_user(request, db)
    team_ids = await get_user_team_ids(db, user.id)
    if team_id not in team_ids:
        raise HTTPException(status_code=403, detail="해당 팀에 접근 권한이 없습니다.")

    recs = await generate_recommendations(db, team_id, user.id)
    await db.commit()
    return {"recommendations": recs, "count": len(recs)}


@router.post("/recommendations/{rec_id}/dismiss")
@limiter.limit("10/minute")
async def dismiss(
    rec_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """MCP 추천 닫기"""
    user = await require_current_user(request, db)
    if not await dismiss_recommendation(db, user.id, rec_id):
        raise HTTPException(status_code=404, detail="추천을 찾을 수 없습니다.")
    return {"message": "추천이 닫혔습니다."}


@router.get("/catalog")
@limiter.limit("30/minute")
async def catalog(request: Request, db: AsyncSession = Depends(get_db)):
    """MCP 카탈로그 (연결 가능한 MCP 목록)"""
    await require_current_user(request, db)
    return {
        "catalog": [
            {
                "key": k,
                "name": v["name"],
                "description": v["description"],
                "keywords": v["keywords"],
            }
            for k, v in MCP_CATALOG.items()
        ]
    }


@router.get("/patterns")
@limiter.limit("10/minute")
async def patterns(
    request: Request,
    team_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """팀 업무 패턴 분석 결과"""
    user = await require_current_user(request, db)
    team_ids = await get_user_team_ids(db, user.id)
    if team_id not in team_ids:
        raise HTTPException(status_code=403, detail="해당 팀에 접근 권한이 없습니다.")

    result = await analyze_team_patterns(db, team_id)
    return result
