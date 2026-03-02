"""문서 관리 + 계약 검토 프로세스 API"""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import (
    get_db, Project, Document, DocumentReview, User, TeamMember, utc_now,
)
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.services.document_service import DocumentService
from app.services.sheets_service import SheetsService
from app.schemas.document import (
    DocumentCreate, DocumentUpdate, DocumentStatusUpdate, DocumentResponse,
    DocumentListResponse, GenerateTasksRequest,
    ReviewCreate, ReviewSubmit, ReviewResponse,
    AIHighlightsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()
doc_service = DocumentService()


# ── 헬퍼 ──

async def _verify_project_access(db: AsyncSession, project_id: int, user_id: int) -> Project:
    """프로젝트 접근 권한 확인"""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    # 본인 프로젝트이거나 팀 멤버인 경우 접근 가능
    if project.user_id == user_id:
        return project

    if project.team_id:
        result = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == project.team_id,
                TeamMember.user_id == user_id,
            )
        )
        if result.scalar_one_or_none():
            return project

    raise HTTPException(status_code=403, detail="접근 권한이 없습니다")


async def _verify_document_access(db: AsyncSession, document_id: int, user_id: int) -> Document:
    """문서 접근 권한 확인 (문서가 속한 프로젝트 기준)"""
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    await _verify_project_access(db, doc.project_id, user_id)
    return doc


def _to_response(doc: Document, uploader_name: str | None = None, review_count: int = 0) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        project_id=doc.project_id,
        user_id=doc.user_id,
        document_type=doc.document_type,
        title=doc.title,
        file_name=doc.file_name,
        stored_path=None,  # 보안: 실제 경로 노출 방지
        status=doc.status,
        version=doc.version,
        parent_id=doc.parent_id,
        ai_analysis=doc.ai_analysis,
        google_sheet_id=doc.google_sheet_id,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        uploader_name=uploader_name,
        review_count=review_count,
    )


# ══════════════════════════════════════════
#  문서 CRUD
# ══════════════════════════════════════════

@router.post("/projects/{project_id}/documents", response_model=DocumentResponse, status_code=201)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    project_id: int,
    document_type: str = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """문서 업로드 + AI 분석"""
    user = await require_current_user(request, db)
    await _verify_project_access(db, project_id, user.id)

    # 유형 검증
    if document_type not in ("estimate", "contract", "proposal", "other"):
        raise HTTPException(status_code=400, detail="유효하지 않은 문서 유형입니다")
    if not title or len(title) > 300:
        raise HTTPException(status_code=400, detail="제목은 1~300자 이내로 입력해주세요")

    try:
        doc = await doc_service.upload_document(
            db=db,
            project_id=project_id,
            user_id=user.id,
            document_type=document_type,
            title=title,
            file=file,
        )

        # 업로드 후 자동 AI 분석 시작
        try:
            doc = await doc_service.analyze_document(db, doc.id)
        except Exception as e:
            logger.warning(f"자동 AI 분석 실패 (document_id={doc.id}): {e}")
            # 분석 실패해도 업로드는 성공 처리

        return _to_response(doc, uploader_name=user.name or user.email)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    request: Request,
    project_id: int,
    document_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 문서 목록 조회"""
    user = await require_current_user(request, db)
    await _verify_project_access(db, project_id, user.id)

    docs = await doc_service.list_documents(db, project_id, document_type)

    # 업로더 이름 조회
    user_ids = {d.user_id for d in docs}
    users_map = {}
    for uid in user_ids:
        u = await db.get(User, uid)
        if u:
            users_map[uid] = u.name or u.email

    # 검토 수 조회
    review_counts = {}
    for d in docs:
        reviews = await doc_service.list_reviews(db, d.id)
        review_counts[d.id] = len(reviews)

    responses = [
        _to_response(d, uploader_name=users_map.get(d.user_id), review_count=review_counts.get(d.id, 0))
        for d in docs
    ]
    return DocumentListResponse(documents=responses, total=len(responses))


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """문서 상세 조회 (분석 결과 포함)"""
    user = await require_current_user(request, db)
    doc = await _verify_document_access(db, document_id, user.id)
    uploader = await db.get(User, doc.user_id)
    reviews = await doc_service.list_reviews(db, doc.id)
    return _to_response(
        doc,
        uploader_name=(uploader.name or uploader.email) if uploader else None,
        review_count=len(reviews),
    )


@router.put("/documents/{document_id}", response_model=DocumentResponse)
@limiter.limit("20/minute")
async def update_document(
    request: Request,
    document_id: int,
    data: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """문서 정보 수정"""
    user = await require_current_user(request, db)
    await _verify_document_access(db, document_id, user.id)

    try:
        doc = await doc_service.update_document(db, document_id, data.model_dump(exclude_none=True))
        return _to_response(doc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """문서 삭제"""
    user = await require_current_user(request, db)
    await _verify_document_access(db, document_id, user.id)

    try:
        await doc_service.delete_document(db, document_id, user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/documents/{document_id}/status", response_model=DocumentResponse)
async def change_document_status(
    request: Request,
    document_id: int,
    data: DocumentStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """문서 상태 변경"""
    user = await require_current_user(request, db)
    await _verify_document_access(db, document_id, user.id)

    try:
        doc = await doc_service.update_status(db, document_id, data.status, user.id)
        return _to_response(doc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ══════════════════════════════════════════
#  문서에서 업무 생성
# ══════════════════════════════════════════

@router.post("/documents/{document_id}/generate-tasks")
@limiter.limit("10/minute")
async def generate_tasks_from_document(
    request: Request,
    document_id: int,
    data: GenerateTasksRequest,
    db: AsyncSession = Depends(get_db),
):
    """AI 분석 결과에서 업무 일괄 생성"""
    user = await require_current_user(request, db)
    await _verify_document_access(db, document_id, user.id)

    try:
        tasks = await doc_service.generate_tasks_from_document(db, document_id, data.selected_task_indices, user.id)
        return {"success": True, "message": f"{len(tasks)}건의 업무가 생성되었습니다", "tasks": tasks}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ══════════════════════════════════════════
#  버전 관리
# ══════════════════════════════════════════

@router.get("/documents/{document_id}/versions")
async def get_version_history(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """버전 이력 조회"""
    user = await require_current_user(request, db)
    await _verify_document_access(db, document_id, user.id)

    versions = await doc_service.get_version_history(db, document_id)
    return {
        "versions": [
            {
                "id": v.id,
                "version": v.version,
                "file_name": v.file_name,
                "status": v.status,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]
    }


@router.post("/documents/{document_id}/new-version", response_model=DocumentResponse, status_code=201)
@limiter.limit("10/minute")
async def upload_new_version(
    request: Request,
    document_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """새 버전 업로드"""
    user = await require_current_user(request, db)
    await _verify_document_access(db, document_id, user.id)

    try:
        new_doc = await doc_service.create_new_version(db, document_id, user.id, file)
        # 자동 AI 분석
        try:
            new_doc = await doc_service.analyze_document(db, new_doc.id)
        except Exception as e:
            logger.warning(f"새 버전 자동 AI 분석 실패: {e}")

        return _to_response(new_doc, uploader_name=user.name or user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ══════════════════════════════════════════
#  문서 파일 다운로드
# ══════════════════════════════════════════

@router.get("/documents/{document_id}/download")
async def download_document(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """문서 파일 다운로드"""
    user = await require_current_user(request, db)
    doc = await _verify_document_access(db, document_id, user.id)

    if not doc.stored_path:
        raise HTTPException(status_code=404, detail="다운로드할 파일이 없습니다")

    file_path = Path(doc.stored_path).resolve()
    docs_dir = Path("uploads/documents").resolve()
    if not str(file_path).startswith(str(docs_dir)):
        raise HTTPException(status_code=403, detail="잘못된 파일 경로입니다")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    return FileResponse(
        path=str(file_path),
        filename=doc.file_name or file_path.name,
        media_type="application/octet-stream",
    )


# ══════════════════════════════════════════
#  계약 검토 프로세스
# ══════════════════════════════════════════

@router.post("/documents/{document_id}/reviews", response_model=ReviewResponse, status_code=201)
@limiter.limit("10/minute")
async def add_reviewer(
    request: Request,
    document_id: int,
    data: ReviewCreate,
    db: AsyncSession = Depends(get_db),
):
    """검토자 지정"""
    user = await require_current_user(request, db)
    await _verify_document_access(db, document_id, user.id)

    # 검토자 존재 확인
    reviewer = await db.get(User, data.reviewer_id)
    if not reviewer:
        raise HTTPException(status_code=404, detail="검토자를 찾을 수 없습니다")

    try:
        review = await doc_service.add_reviewer(db, document_id, data.reviewer_id, user.id)
        return ReviewResponse(
            id=review.id,
            document_id=review.document_id,
            reviewer_id=review.reviewer_id,
            reviewer_name=reviewer.name,
            reviewer_email=reviewer.email,
            status=review.status,
            comment=review.comment,
            created_at=review.created_at,
            reviewed_at=review.reviewed_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/documents/{document_id}/reviews", response_model=list[ReviewResponse])
async def list_reviews(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """검토 현황 조회"""
    user = await require_current_user(request, db)
    await _verify_document_access(db, document_id, user.id)

    reviews = await doc_service.list_reviews(db, document_id)

    result = []
    for r in reviews:
        reviewer = await db.get(User, r.reviewer_id)
        result.append(ReviewResponse(
            id=r.id,
            document_id=r.document_id,
            reviewer_id=r.reviewer_id,
            reviewer_name=reviewer.name if reviewer else None,
            reviewer_email=reviewer.email if reviewer else None,
            status=r.status,
            comment=r.comment,
            created_at=r.created_at,
            reviewed_at=r.reviewed_at,
        ))
    return result


@router.patch("/documents/{document_id}/reviews/{review_id}", response_model=ReviewResponse)
async def submit_review(
    request: Request,
    document_id: int,
    review_id: int,
    data: ReviewSubmit,
    db: AsyncSession = Depends(get_db),
):
    """검토 결과 제출"""
    user = await require_current_user(request, db)
    await _verify_document_access(db, document_id, user.id)

    # 검토자 본인만 제출 가능
    review = await db.get(DocumentReview, review_id)
    if not review or review.reviewer_id != user.id:
        raise HTTPException(status_code=403, detail="본인의 검토만 제출할 수 있습니다")

    try:
        review = await doc_service.submit_review(db, document_id, review_id, data.status, data.comment)
        return ReviewResponse(
            id=review.id,
            document_id=review.document_id,
            reviewer_id=review.reviewer_id,
            reviewer_name=user.name,
            reviewer_email=user.email,
            status=review.status,
            comment=review.comment,
            created_at=review.created_at,
            reviewed_at=review.reviewed_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ══════════════════════════════════════════
#  AI 핵심 조항 분석
# ══════════════════════════════════════════

@router.post("/documents/{document_id}/ai-highlights", response_model=AIHighlightsResponse)
@limiter.limit("3/minute")
async def analyze_ai_highlights(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """AI 핵심 조항 분석 (계약서 전용)"""
    user = await require_current_user(request, db)
    await _verify_document_access(db, document_id, user.id)

    try:
        result = await doc_service.analyze_key_terms(db, document_id)
        return AIHighlightsResponse(
            key_terms=result.get("key_terms", []),
            summary=result.get("summary"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════
#  Google Sheets 연동
# ══════════════════════════════════════════

@router.post("/projects/{project_id}/sheets/create", response_model=DocumentResponse, status_code=201)
@limiter.limit("5/minute")
async def create_google_sheet(
    request: Request,
    project_id: int,
    title: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """새 Google Sheet 생성 (견적서 템플릿)"""
    user = await require_current_user(request, db)
    await _verify_project_access(db, project_id, user.id)

    if not title or len(title) > 300:
        raise HTTPException(status_code=400, detail="제목은 1~300자 이내로 입력해주세요")

    try:

        # 세션에서 Google OAuth 토큰 가져오기
        google_token = request.session.get("google_credentials")
        sheets_svc = SheetsService(credentials=google_token)
        doc = await sheets_svc.create_sheet(db, project_id, user.id, title)
        return _to_response(doc, uploader_name=user.name or user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/sheets/link", response_model=DocumentResponse, status_code=201)
@limiter.limit("10/minute")
async def link_google_sheet(
    request: Request,
    project_id: int,
    sheet_url: str = Form(...),
    title: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """기존 Google Sheet 연결"""
    user = await require_current_user(request, db)
    await _verify_project_access(db, project_id, user.id)

    try:

        google_token = request.session.get("google_credentials")
        sheets_svc = SheetsService(credentials=google_token)
        doc = await sheets_svc.link_sheet(db, project_id, user.id, sheet_url, title)
        return _to_response(doc, uploader_name=user.name or user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/documents/{document_id}/sheet-data")
async def get_sheet_data(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Google Sheet 내용 읽기"""
    user = await require_current_user(request, db)
    await _verify_document_access(db, document_id, user.id)

    try:

        google_token = request.session.get("google_credentials")
        sheets_svc = SheetsService(credentials=google_token)
        return await sheets_svc.read_sheet_data(document_id, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/documents/{document_id}/sheet-parse")
@limiter.limit("5/minute")
async def parse_sheet_with_ai(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """AI로 Google Sheet 내용 파싱"""
    user = await require_current_user(request, db)
    await _verify_document_access(db, document_id, user.id)

    try:

        google_token = request.session.get("google_credentials")
        sheets_svc = SheetsService(credentials=google_token)
        result = await sheets_svc.parse_sheet_with_ai(document_id, db)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
