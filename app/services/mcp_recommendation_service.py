"""업무 패턴 분석 + MCP 추천 서비스 — 3차 개발 S7-1, S7-2 (선택)

활동 로그 분석 → 도구 사용 패턴 추출 → 적합한 MCP 추천
"""
import logging
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    ActivityLog, McpRecommendation, utc_now,
)

logger = logging.getLogger(__name__)

# MCP 도구 정의 + 키워드 매핑
MCP_CATALOG = {
    "figma": {
        "name": "Figma",
        "description": "디자인 시안 조회, 스크린샷, 메타데이터 확인",
        "keywords": ["디자인", "시안", "figma", "UI", "UX", "와이어프레임", "목업"],
        "target_types": ["document"],
        "actions": ["create", "update"],
        "min_score": 5,
    },
    "google_calendar": {
        "name": "Google Calendar",
        "description": "일정 관리, 마감일 연동, 미팅 스케줄",
        "keywords": ["일정", "미팅", "회의", "마감", "calendar", "스케줄"],
        "target_types": ["task"],
        "actions": ["create", "assign", "status_change"],
        "min_score": 10,
    },
    "google_drive": {
        "name": "Google Drive",
        "description": "문서 공유, 파일 관리, 공동 편집",
        "keywords": ["문서", "파일", "공유", "drive", "첨부", "업로드"],
        "target_types": ["document"],
        "actions": ["create", "update"],
        "min_score": 8,
    },
    "slack": {
        "name": "Slack",
        "description": "팀 커뮤니케이션, 알림 연동",
        "keywords": ["메시지", "채팅", "알림", "공유", "전달"],
        "target_types": ["comment"],
        "actions": ["comment", "create"],
        "min_score": 10,
    },
    "notion": {
        "name": "Notion",
        "description": "문서화, 위키, 지식 베이스",
        "keywords": ["문서", "위키", "정리", "기록", "노트"],
        "target_types": ["document", "project"],
        "actions": ["create", "update"],
        "min_score": 8,
    },
}


async def analyze_team_patterns(
    db: AsyncSession,
    team_id: int,
) -> dict:
    """팀의 활동 패턴 분석

    Returns: {
        "total_activities": int,
        "action_counts": {"create": N, "update": N, ...},
        "target_type_counts": {"task": N, "document": N, ...},
        "keyword_hits": {"figma": N, "calendar": N, ...},
    }
    """
    # 최근 30일 활동 로그 조회
    from datetime import timedelta
    cutoff = utc_now() - timedelta(days=30)

    result = await db.execute(
        select(ActivityLog).where(
            ActivityLog.team_id == team_id,
            ActivityLog.created_at >= cutoff,
        ).limit(1000)
    )
    logs = result.scalars().all()

    action_counts = Counter()
    target_counts = Counter()
    keyword_hits = Counter()

    for log in logs:
        action_counts[log.action] += 1
        target_counts[log.target_type] += 1

        # 키워드 분석 (target_name + detail)
        text = f"{log.target_name or ''} {log.detail or ''}".lower()
        for mcp_key, mcp_info in MCP_CATALOG.items():
            for keyword in mcp_info["keywords"]:
                if keyword.lower() in text:
                    keyword_hits[mcp_key] += 1
                    break

    return {
        "total_activities": len(logs),
        "action_counts": dict(action_counts),
        "target_type_counts": dict(target_counts),
        "keyword_hits": dict(keyword_hits),
    }


async def generate_recommendations(
    db: AsyncSession,
    team_id: int,
    user_id: int,
) -> list[dict]:
    """MCP 추천 생성 (S7-2)

    활동 패턴 분석 결과를 기반으로 적합한 MCP 추천
    """
    patterns = await analyze_team_patterns(db, team_id)

    recommendations = []
    for mcp_key, mcp_info in MCP_CATALOG.items():
        score = 0

        # 키워드 히트 점수
        keyword_score = patterns["keyword_hits"].get(mcp_key, 0)
        score += keyword_score * 2

        # target_type 매칭 점수
        for tt in mcp_info["target_types"]:
            score += patterns["target_type_counts"].get(tt, 0) // 5

        # action 매칭 점수
        for act in mcp_info["actions"]:
            score += patterns["action_counts"].get(act, 0) // 10

        if score >= mcp_info["min_score"]:
            # 이미 추천된 적 있는지 확인
            existing = await db.execute(
                select(McpRecommendation).where(
                    McpRecommendation.team_id == team_id,
                    McpRecommendation.user_id == user_id,
                    McpRecommendation.mcp_name == mcp_key,
                    McpRecommendation.is_dismissed == False,  # noqa: E712
                )
            )
            if existing.scalar_one_or_none():
                continue

            rec = McpRecommendation(
                team_id=team_id,
                user_id=user_id,
                mcp_name=mcp_key,
                reason=_build_reason(mcp_key, mcp_info, patterns),
                score=score,
            )
            db.add(rec)
            recommendations.append({
                "mcp_name": mcp_key,
                "display_name": mcp_info["name"],
                "description": mcp_info["description"],
                "reason": rec.reason,
                "score": score,
            })

    if recommendations:
        await db.flush()

    return recommendations


def _build_reason(mcp_key: str, mcp_info: dict, patterns: dict) -> str:
    """추천 사유 생성"""
    keyword_count = patterns["keyword_hits"].get(mcp_key, 0)
    total = patterns["total_activities"]

    if keyword_count > 0:
        return f"최근 30일간 '{mcp_info['keywords'][0]}' 관련 활동이 {keyword_count}건 감지되었습니다. {mcp_info['name']}을(를) 연결하면 업무 효율이 향상됩니다."
    else:
        return f"팀의 {', '.join(mcp_info['target_types'])} 활동 패턴을 분석한 결과, {mcp_info['name']} 연동이 도움이 될 수 있습니다."


async def get_user_recommendations(
    db: AsyncSession,
    user_id: int,
) -> list[dict]:
    """사용자의 활성 MCP 추천 조회"""
    result = await db.execute(
        select(McpRecommendation).where(
            McpRecommendation.user_id == user_id,
            McpRecommendation.is_dismissed == False,  # noqa: E712
        ).order_by(McpRecommendation.score.desc())
    )
    recs = result.scalars().all()

    return [{
        "id": r.id,
        "mcp_name": r.mcp_name,
        "display_name": MCP_CATALOG.get(r.mcp_name, {}).get("name", r.mcp_name),
        "description": MCP_CATALOG.get(r.mcp_name, {}).get("description", ""),
        "reason": r.reason,
        "score": r.score,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in recs]


async def dismiss_recommendation(
    db: AsyncSession,
    user_id: int,
    recommendation_id: int,
) -> bool:
    """MCP 추천 닫기"""
    rec = await db.get(McpRecommendation, recommendation_id)
    if not rec or rec.user_id != user_id:
        return False
    rec.is_dismissed = True
    await db.commit()
    return True
