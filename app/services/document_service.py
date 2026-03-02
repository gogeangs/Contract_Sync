import json
import logging
import uuid
from pathlib import Path

import aiofiles
from fastapi import UploadFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import settings
from app.database import Document, DocumentReview, Project, Task, User, Notification, ActivityLog, utc_now
from app.parsers import ParserFactory
from app.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)

# 지원 확장자
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".hwp", ".hwpx", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}

# magic bytes
MAGIC_BYTES = {
    ".pdf": (b"%PDF",),
    ".docx": (b"PK\x03\x04",),
    ".hwp": (b"\xd0\xcf\x11\xe0", b"PK\x03\x04"),
    ".hwpx": (b"PK\x03\x04",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG",),
    ".tiff": (b"II\x2a\x00", b"MM\x00\x2a"),
    ".tif": (b"II\x2a\x00", b"MM\x00\x2a"),
    ".bmp": (b"BM",),
    ".webp": (b"RIFF",),
}


class DocumentService:
    """문서 관리 서비스"""

    def __init__(self):
        self.docs_dir = Path(settings.upload_dir) / "documents"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size = settings.max_file_size_mb * 1024 * 1024

    # ── 문서 업로드 ──

    async def upload_document(
        self,
        db: AsyncSession,
        project_id: int,
        user_id: int,
        document_type: str,
        title: str,
        file: UploadFile,
    ) -> Document:
        """문서 업로드 + AI 분석 시작"""
        # 파일 저장
        original_name = file.filename or "unknown"
        extension = Path(original_name).suffix.lower()

        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"지원하지 않는 파일 형식입니다. 지원: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

        # 저장 경로: documents/{project_id}/{uuid}.ext
        project_dir = self.docs_dir / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{uuid.uuid4()}{extension}"
        stored_path = project_dir / unique_name

        # 스트리밍 저장 + magic bytes 검증
        total_size = 0
        first_chunk = True
        async with aiofiles.open(stored_path, "wb") as f:
            while chunk := await file.read(8192):
                if first_chunk:
                    first_chunk = False
                    expected = MAGIC_BYTES.get(extension)
                    if expected and not any(chunk.startswith(m) for m in expected):
                        raise ValueError("파일이 손상되었거나 형식이 올바르지 않습니다")
                total_size += len(chunk)
                if total_size > self.max_file_size:
                    stored_path.unlink(missing_ok=True)
                    raise ValueError(f"파일 크기는 {settings.max_file_size_mb}MB를 초과할 수 없습니다")
                await f.write(chunk)

        # DB 저장
        doc = Document(
            project_id=project_id,
            user_id=user_id,
            document_type=document_type,
            title=title,
            file_name=original_name,
            stored_path=str(stored_path),
            status="uploaded",
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        # 활동 로그
        db.add(ActivityLog(
            project_id=project_id,
            user_id=user_id,
            action="create",
            target_type="document",
            target_name=title,
            detail=json.dumps({"document_type": document_type, "file_name": original_name}, ensure_ascii=False),
        ))
        await db.commit()

        return doc

    # ── AI 분석 ──

    async def analyze_document(self, db: AsyncSession, document_id: int) -> Document:
        """문서 AI 분석 실행"""
        doc = await self._get_document(db, document_id)
        if not doc.stored_path:
            raise ValueError("파일이 없는 문서는 분석할 수 없습니다")

        file_path = Path(doc.stored_path)
        if not file_path.exists():
            raise ValueError("파일을 찾을 수 없습니다")

        # 상태 변경: analyzing
        doc.status = "analyzing"
        await db.commit()

        try:
            # 파일 파싱
            extension = file_path.suffix.lower()
            parser = ParserFactory.get_parser(extension)
            parse_result = await parser.parse(str(file_path))

            # AI 분석 프롬프트 (문서 유형별)
            gemini = GeminiService()
            ai_result = await self._run_ai_analysis(gemini, doc.document_type, parse_result)

            # 결과 저장
            doc.ai_analysis = ai_result
            doc.raw_text = parse_result.text if parse_result.has_text else ""
            doc.status = "review_pending"
            await db.commit()
            await db.refresh(doc)

            return doc

        except Exception as e:
            logger.error(f"문서 분석 실패 (id={document_id}): {e}")
            doc.status = "uploaded"
            await db.commit()
            raise RuntimeError(f"문서 분석에 실패했습니다: {e}")

    async def _run_ai_analysis(self, gemini: GeminiService, document_type: str, parse_result) -> dict:
        """문서 유형별 AI 분석 실행"""
        if document_type == "contract":
            # 기존 계약서 분석 로직 재사용
            schedule, tasks, raw_text = await gemini.extract_schedule(
                text=parse_result.text if parse_result.has_text else "",
                images=parse_result.images if parse_result.has_images else None,
            )
            return {
                "type": "contract",
                "contract_schedule": schedule.model_dump(),
                "task_list": [t.model_dump() for t in tasks],
                "raw_text": raw_text,
            }
        elif document_type == "estimate":
            return await self._analyze_estimate(gemini, parse_result)
        elif document_type == "proposal":
            return await self._analyze_proposal(gemini, parse_result)
        else:
            # 기타 문서: 기본 텍스트 추출
            return {"type": "other", "summary": parse_result.text[:2000] if parse_result.has_text else ""}

    async def _analyze_estimate(self, gemini: GeminiService, parse_result) -> dict:
        """견적서 AI 분석"""
        prompt = """당신은 한국어 견적서 분석 전문가입니다.
다음 견적서에서 항목을 추출해 주세요.

아래 JSON 형식으로 응답:
{
    "type": "estimate",
    "estimate_items": [
        {
            "name": "항목명",
            "quantity": 수량,
            "unit": "단위(식/건/EA 등)",
            "unit_price": 단가(숫자),
            "amount": 금액(숫자),
            "estimated_days": 예상일수 또는 null
        }
    ],
    "total_amount": 총액(숫자),
    "estimated_duration_days": 총 예상 기간(일) 또는 null,
    "notes": "특이사항"
}"""
        from google.genai import types

        text = parse_result.text[:12000] if parse_result.has_text else ""
        contents = f"{prompt}\n\n---\n{text}\n---" if text else prompt

        parts = [types.Part.from_text(contents)]
        if parse_result.has_images:
            for img in parse_result.images:
                parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))

        response = await gemini.client.aio.models.generate_content(
            model=gemini.model,
            contents=types.Content(parts=parts),
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                http_options=types.HttpOptions(timeout=120_000),
            ),
        )
        return gemini._parse_json_response(response.text)

    async def _analyze_proposal(self, gemini: GeminiService, parse_result) -> dict:
        """제안서 AI 분석"""
        prompt = """당신은 한국어 제안서 분석 전문가입니다.
다음 제안서에서 핵심 조건을 추출해 주세요.

아래 JSON 형식으로 응답:
{
    "type": "proposal",
    "key_conditions": [
        {"category": "범위/일정/예산/인력/기타", "content": "내용", "importance": "높음/보통/낮음"}
    ],
    "scope": "프로젝트 범위 요약",
    "timeline": "일정 요약",
    "budget": "예산 정보",
    "notes": "특이사항"
}"""
        from google.genai import types

        text = parse_result.text[:12000] if parse_result.has_text else ""
        contents = f"{prompt}\n\n---\n{text}\n---" if text else prompt

        parts = [types.Part.from_text(contents)]
        if parse_result.has_images:
            for img in parse_result.images:
                parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))

        response = await gemini.client.aio.models.generate_content(
            model=gemini.model,
            contents=types.Content(parts=parts),
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                http_options=types.HttpOptions(timeout=120_000),
            ),
        )
        return gemini._parse_json_response(response.text)

    # ── AI 핵심 조항 분석 (계약서 전용) ──

    async def analyze_key_terms(self, db: AsyncSession, document_id: int) -> dict:
        """계약서 핵심 조항 AI 분석"""
        doc = await self._get_document(db, document_id)
        if doc.document_type != "contract":
            raise ValueError("핵심 조항 분석은 계약서만 가능합니다")

        text = doc.raw_text or ""
        if not text and doc.ai_analysis:
            text = doc.ai_analysis.get("raw_text", "")
        if not text:
            raise ValueError("분석할 텍스트가 없습니다. 먼저 문서를 분석해 주세요.")

        from google.genai import types

        prompt = """당신은 한국어 계약서 법률 분석 전문가입니다.
다음 계약서에서 핵심 조항을 분석해 주세요.

분석 대상:
1. 계약 금액 - 총액, 부가세 포함 여부
2. 지급 조건 - 착수금/중도금/잔금 비율, 지급 시점
3. 지연 배상금 - 지연 시 배상 조건, 배상률
4. 하자 보수 - 하자 보증 기간, 범위
5. 지적재산권 - 저작권 귀속, 사용 권한
6. 비밀유지 - 비밀유지 기간, 범위

아래 JSON 형식으로 응답:
{
    "key_terms": [
        {
            "category": "계약금액/지급조건/지연배상금/하자보수/지적재산권/비밀유지/기타",
            "title": "조항 제목",
            "content": "조항 내용 요약",
            "risk_level": "높음/보통/낮음",
            "note": "주의사항 또는 null"
        }
    ],
    "summary": "계약서 전체 요약 (2-3문장)"
}"""

        gemini = GeminiService()
        response = await gemini.client.aio.models.generate_content(
            model=gemini.model,
            contents=f"{prompt}\n\n---\n{text[:12000]}\n---",
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                http_options=types.HttpOptions(timeout=120_000),
            ),
        )
        result = gemini._parse_json_response(response.text)

        # ai_analysis에 key_terms 추가 저장
        if doc.ai_analysis is None:
            doc.ai_analysis = {}
        analysis = dict(doc.ai_analysis)
        analysis["key_terms"] = result.get("key_terms", [])
        analysis["summary"] = result.get("summary", "")
        doc.ai_analysis = analysis
        await db.commit()

        return result

    # ── 문서에서 업무 생성 ──

    async def generate_tasks_from_document(
        self, db: AsyncSession, document_id: int, selected_indices: list[int], user_id: int
    ) -> list[dict]:
        """AI 분석 결과에서 선택한 업무를 독립 Task 테이블에 생성"""
        doc = await self._get_document(db, document_id)
        if not doc.ai_analysis:
            raise ValueError("AI 분석 결과가 없습니다. 먼저 문서를 분석해 주세요.")

        # 분석 결과에서 task_list 추출
        task_list = doc.ai_analysis.get("task_list", [])
        if not task_list:
            # 견적서의 경우 estimate_items에서 추출
            items = doc.ai_analysis.get("estimate_items", [])
            task_list = [
                {"task_name": item.get("name", ""), "phase": "견적 기반", "priority": "보통"}
                for item in items
            ]

        if not task_list:
            raise ValueError("생성할 업무가 없습니다")

        # 선택된 업무만 필터
        selected_tasks = []
        for idx in selected_indices:
            if 0 <= idx < len(task_list):
                selected_tasks.append(task_list[idx])

        if not selected_tasks:
            raise ValueError("유효한 업무가 선택되지 않았습니다")

        # 프로젝트 확인
        project = await db.get(Project, doc.project_id)
        if not project:
            raise ValueError("프로젝트를 찾을 수 없습니다")

        # Task 레코드 생성 (task.id 기반 task_code — task_service.create()와 동일 방식)
        new_tasks = []
        for task_data in selected_tasks:
            task = Task(
                project_id=doc.project_id,
                user_id=user_id,
                team_id=project.team_id,
                task_name=task_data.get("task_name", ""),
                phase=task_data.get("phase", ""),
                due_date=task_data.get("due_date"),
                priority=task_data.get("priority", "보통"),
                status="pending",
            )
            db.add(task)
            await db.flush()
            task.task_code = f"TASK-{task.id:03d}"
            new_tasks.append(task)

        # 활동 로그
        db.add(ActivityLog(
            project_id=doc.project_id,
            team_id=project.team_id,
            user_id=user_id,
            action="create",
            target_type="task",
            target_name=f"문서 '{doc.title}'에서 업무 {len(new_tasks)}건 생성",
            detail=json.dumps({"source_document_id": doc.id, "task_count": len(new_tasks)}, ensure_ascii=False),
        ))
        await db.commit()

        # 응답용 dict 변환
        return [
            {
                "id": t.id,
                "task_code": t.task_code,
                "task_name": t.task_name,
                "phase": t.phase,
                "due_date": t.due_date,
                "priority": t.priority,
                "status": t.status,
            }
            for t in new_tasks
        ]

    # ── 버전 관리 ──

    async def create_new_version(
        self,
        db: AsyncSession,
        parent_document_id: int,
        user_id: int,
        file: UploadFile,
    ) -> Document:
        """기존 문서의 새 버전 업로드"""
        parent = await self._get_document(db, parent_document_id)

        # 파일 저장 (기존 upload 로직 재사용)
        new_doc = await self.upload_document(
            db=db,
            project_id=parent.project_id,
            user_id=user_id,
            document_type=parent.document_type,
            title=parent.title,
            file=file,
        )

        # 버전 정보 설정
        new_doc.parent_id = parent.id
        new_doc.version = parent.version + 1
        await db.commit()
        await db.refresh(new_doc)

        return new_doc

    # ── CRUD ──

    async def get_document(self, db: AsyncSession, document_id: int) -> Document:
        return await self._get_document(db, document_id)

    async def list_documents(
        self, db: AsyncSession, project_id: int, document_type: str | None = None
    ) -> list[Document]:
        """프로젝트의 문서 목록 조회"""
        query = (
            select(Document)
            .where(Document.project_id == project_id)
            .order_by(Document.created_at.desc())
        )
        if document_type:
            query = query.where(Document.document_type == document_type)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def update_document(self, db: AsyncSession, document_id: int, data: dict) -> Document:
        """문서 정보 수정"""
        doc = await self._get_document(db, document_id)
        for key, value in data.items():
            if value is not None and hasattr(doc, key):
                setattr(doc, key, value)
        doc.updated_at = utc_now()
        await db.commit()
        await db.refresh(doc)
        return doc

    async def update_status(self, db: AsyncSession, document_id: int, status: str, user_id: int) -> Document:
        """문서 상태 변경"""
        valid_transitions = {
            "uploaded": {"analyzing"},
            "analyzing": {"review_pending", "uploaded"},
            "review_pending": {"revision_requested", "confirmed"},
            "revision_requested": {"review_pending", "confirmed"},
            "confirmed": set(),
        }
        doc = await self._get_document(db, document_id)
        allowed = valid_transitions.get(doc.status, set())
        if status not in allowed:
            raise ValueError(f"'{doc.status}' → '{status}' 상태 변경이 불가합니다")

        doc.status = status
        doc.updated_at = utc_now()
        await db.commit()
        await db.refresh(doc)

        # 활동 로그
        db.add(ActivityLog(
            project_id=doc.project_id,
            user_id=user_id,
            action="status_change",
            target_type="document",
            target_name=doc.title,
            detail=json.dumps({"new_status": status}, ensure_ascii=False),
        ))
        await db.commit()

        return doc

    async def delete_document(self, db: AsyncSession, document_id: int, user_id: int) -> None:
        """문서 삭제"""
        doc = await self._get_document(db, document_id)

        # 파일 삭제
        if doc.stored_path:
            path = Path(doc.stored_path)
            path.unlink(missing_ok=True)

        project_id = doc.project_id
        title = doc.title

        await db.delete(doc)
        await db.commit()

        # 활동 로그
        db.add(ActivityLog(
            project_id=project_id,
            user_id=user_id,
            action="delete",
            target_type="document",
            target_name=title,
        ))
        await db.commit()

    async def get_version_history(self, db: AsyncSession, document_id: int) -> list[Document]:
        """문서 버전 이력 조회"""
        doc = await self._get_document(db, document_id)

        # 최상위 부모 찾기
        root_id = doc.id
        current = doc
        while current.parent_id:
            root_id = current.parent_id
            current = await self._get_document(db, current.parent_id)

        # 같은 루트를 가진 모든 버전 조회
        query = (
            select(Document)
            .where(
                (Document.id == root_id) | (Document.parent_id == root_id)
            )
            .order_by(Document.version.asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    # ── 검토 관리 ──

    async def add_reviewer(
        self, db: AsyncSession, document_id: int, reviewer_id: int, requester_id: int
    ) -> DocumentReview:
        """검토자 지정"""
        doc = await self._get_document(db, document_id)
        if doc.document_type != "contract":
            raise ValueError("검토 프로세스는 계약서만 지원합니다")
        if doc.status not in ("review_pending", "revision_requested"):
            raise ValueError("검토 대기 또는 수정 요청 상태에서만 검토자를 지정할 수 있습니다")

        # 중복 검토자 확인
        existing = await db.execute(
            select(DocumentReview).where(
                DocumentReview.document_id == document_id,
                DocumentReview.reviewer_id == reviewer_id,
                DocumentReview.status == "pending",
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("이미 지정된 검토자입니다")

        review = DocumentReview(
            document_id=document_id,
            reviewer_id=reviewer_id,
        )
        db.add(review)
        await db.commit()
        await db.refresh(review)

        # 검토자에게 알림
        reviewer = await db.get(User, reviewer_id)
        requester = await db.get(User, requester_id)
        db.add(Notification(
            user_id=reviewer_id,
            type="document_review",
            title="문서 검토 요청",
            message=f"{requester.name or requester.email}님이 '{doc.title}' 문서의 검토를 요청했습니다.",
            link=json.dumps({"project_id": doc.project_id, "document_id": doc.id}),
        ))
        await db.commit()

        return review

    async def submit_review(
        self, db: AsyncSession, document_id: int, review_id: int, status: str, comment: str | None
    ) -> DocumentReview:
        """검토 결과 제출"""
        review = await db.get(DocumentReview, review_id)
        if not review or review.document_id != document_id:
            raise ValueError("검토를 찾을 수 없습니다")
        if review.status != "pending":
            raise ValueError("이미 처리된 검토입니다")

        review.status = status
        review.comment = comment
        review.reviewed_at = utc_now()
        await db.commit()
        await db.refresh(review)

        # 문서 상태 자동 갱신
        doc = await self._get_document(db, document_id)
        if status == "rejected":
            doc.status = "revision_requested"
            await db.commit()

        # 모든 검토자가 승인했으면 자동 확정
        all_reviews = await db.execute(
            select(DocumentReview).where(DocumentReview.document_id == document_id)
        )
        reviews_list = list(all_reviews.scalars().all())
        if reviews_list and all(r.status == "approved" for r in reviews_list):
            doc.status = "confirmed"
            await db.commit()

        return review

    async def list_reviews(self, db: AsyncSession, document_id: int) -> list[DocumentReview]:
        """검토 현황 조회"""
        result = await db.execute(
            select(DocumentReview)
            .where(DocumentReview.document_id == document_id)
            .order_by(DocumentReview.created_at.asc())
        )
        return list(result.scalars().all())

    # ── 내부 헬퍼 ──

    async def _get_document(self, db: AsyncSession, document_id: int) -> Document:
        doc = await db.get(Document, document_id)
        if not doc:
            raise ValueError("문서를 찾을 수 없습니다")
        return doc
