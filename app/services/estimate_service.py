"""AI 견적서 생성 서비스 — Phase 4"""
import asyncio
import json
import logging

from fastapi import HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Project, Document, Task, utc_now
from app.services.common import get_user_team_ids, access_filter, get_accessible, log_activity
from app.services.gemini_service import GeminiService
from app.services.sheets_service import SheetsService, ESTIMATE_TEMPLATE

logger = logging.getLogger(__name__)


# ── 과거 프로젝트 데이터 수집 ──

async def _gather_past_projects(db: AsyncSession, user) -> list[dict]:
    """접근 가능한 프로젝트에서 과거 견적 참고 데이터 수집 (최근 20건)"""
    team_ids = await get_user_team_ids(db, user.id)
    af = access_filter(Project, user.id, team_ids)

    result = await db.execute(
        select(Project)
        .where(af)
        .order_by(desc(Project.created_at))
        .limit(20)
    )
    projects = result.scalars().all()

    past = []
    for p in projects:
        # 업무 수 조회
        task_q = await db.execute(
            select(Task).where(Task.project_id == p.id)
        )
        tasks = task_q.scalars().all()

        # 해당 프로젝트의 견적 문서에서 ai_analysis 추출
        doc_q = await db.execute(
            select(Document).where(
                Document.project_id == p.id,
                Document.document_type == "estimate",
            ).order_by(desc(Document.created_at)).limit(1)
        )
        estimate_doc = doc_q.scalars().first()

        estimate_items = []
        if estimate_doc and estimate_doc.ai_analysis:
            ai = estimate_doc.ai_analysis
            if isinstance(ai, str):
                try:
                    ai = json.loads(ai)
                except (json.JSONDecodeError, TypeError):
                    ai = {}
            for item in ai.get("items", []):
                estimate_items.append({
                    "name": item.get("name", ""),
                    "amount": item.get("amount", 0),
                    "days": item.get("estimated_days", 0),
                })

        past.append({
            "project_name": p.project_name,
            "project_type": p.project_type or "",
            "contract_amount": p.contract_amount or "미정",
            "duration_days": p.total_duration_days or 0,
            "task_count": len(tasks),
            "estimate_items": estimate_items,
        })

    return past


# ── AI 견적 생성 ──

async def generate_estimate(db: AsyncSession, user, data) -> dict:
    """AI 견적서 생성"""
    past_projects = await _gather_past_projects(db, user)

    context = {
        "project_type": data.project_type,
        "scope_description": data.scope_description,
        "past_projects": past_projects,
    }

    gemini = GeminiService()
    result = await gemini.generate_estimate(context)

    await log_activity(
        db, user.id, "generate", "estimate",
        f"AI 견적서 ({data.project_type})",
        detail=f"총액: {result.get('total_amount', 0):,}원 / {len(result.get('items', []))}건",
    )
    await db.commit()

    return result


# ── Google Sheet 내보내기 ──

async def export_to_sheet(db: AsyncSession, user, data) -> dict:
    """견적서를 Google Sheet로 내보내기"""
    team_ids = await get_user_team_ids(db, user.id)
    project = await get_accessible(db, Project, data.project_id, user.id, team_ids)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    # Google Sheet 생성 (빈 템플릿)
    sheets = SheetsService(credentials=getattr(user, "google_credentials", None))
    doc = await sheets.create_sheet(db, data.project_id, user.id, data.title)

    # 견적 항목 데이터 행 준비
    rows = []
    for i, item in enumerate(data.estimate_data.items, 1):
        note = f"{item.estimated_days}일"
        if item.description:
            note += f" / {item.description}"
        rows.append([
            str(i),
            item.name,
            str(item.quantity),
            item.unit,
            f"{item.unit_price:,}",
            f"{item.amount:,}",
            note,
        ])
    # 합계 행
    rows.append([
        "",
        "합계",
        "",
        "",
        "",
        f"{data.estimate_data.total_amount:,}",
        f"예상 {data.estimate_data.estimated_duration_days}일",
    ])

    # Sheet에 데이터 삽입 (동기 API를 별도 스레드에서 실행)
    try:
        service = sheets.get_sheets_service()

        def _update_sheet():
            service.spreadsheets().values().update(
                spreadsheetId=doc.google_sheet_id,
                range="견적서!A2",
                valueInputOption="RAW",
                body={"values": rows},
            ).execute()

        await asyncio.to_thread(_update_sheet)
    except Exception as e:
        logger.warning(f"Sheet 데이터 삽입 실패 (시트는 생성됨): {e}")

    # Document에 ai_analysis 저장
    doc.ai_analysis = data.estimate_data.model_dump()
    await db.commit()
    await db.refresh(doc)

    sheet_url = f"https://docs.google.com/spreadsheets/d/{doc.google_sheet_id}"

    await log_activity(
        db, user.id, "create", "estimate",
        data.title,
        project_id=data.project_id, team_id=project.team_id,
        detail=f"Google Sheet 내보내기 / {data.estimate_data.total_amount:,}원",
    )
    await db.commit()

    return {
        "document_id": doc.id,
        "google_sheet_id": doc.google_sheet_id,
        "sheet_url": sheet_url,
    }
