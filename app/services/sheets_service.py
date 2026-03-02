"""Google Sheets 연동 서비스

Google Sheets API v4를 사용하여 견적서를 생성/연결/파싱합니다.
OAuth2 인증으로 사용자의 Google Drive에 시트를 생성하거나 기존 시트를 연결합니다.
"""
import json
import logging
import re
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import Document, ActivityLog, utc_now
from app.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)

# 기본 견적서 템플릿 (시트 생성 시 사용)
ESTIMATE_TEMPLATE = {
    "headers": ["No", "항목명", "수량", "단위", "단가", "금액", "비고"],
    "column_widths": [50, 300, 80, 80, 120, 120, 200],
}


class SheetsService:
    """Google Sheets 연동 서비스"""

    def __init__(self, credentials: dict | None = None):
        """
        Args:
            credentials: Google OAuth2 인증 정보 (access_token 포함)
        """
        self.credentials = credentials

    def get_sheets_service(self):
        """Google Sheets API 서비스 객체 생성 (public)"""
        return self._get_service()

    def _get_service(self):
        """Google Sheets API 서비스 객체 생성"""
        if not self.credentials:
            raise ValueError("Google 계정 연동이 필요합니다. 설정에서 Google 계정을 연결해 주세요.")

        try:
            from googleapiclient.discovery import build
            from google.oauth2.credentials import Credentials

            creds = Credentials(
                token=self.credentials.get("access_token"),
                refresh_token=self.credentials.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
            )
            return build("sheets", "v4", credentials=creds)
        except ImportError:
            raise RuntimeError(
                "Google API 클라이언트가 설치되지 않았습니다. "
                "'pip install google-api-python-client google-auth' 를 실행해 주세요."
            )

    def _get_drive_service(self):
        """Google Drive API 서비스 객체 생성"""
        if not self.credentials:
            raise ValueError("Google 계정 연동이 필요합니다.")

        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials

        creds = Credentials(
            token=self.credentials.get("access_token"),
            refresh_token=self.credentials.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
        return build("drive", "v3", credentials=creds)

    # ── 시트 생성 ──

    async def create_sheet(
        self, db: AsyncSession, project_id: int, user_id: int, title: str
    ) -> Document:
        """새 Google Sheet 생성 (견적서 템플릿 적용)"""
        service = self._get_service()

        # 시트 생성
        spreadsheet = service.spreadsheets().create(body={
            "properties": {"title": title},
            "sheets": [{
                "properties": {"title": "견적서"},
                "data": [{
                    "startRow": 0,
                    "startColumn": 0,
                    "rowData": [
                        {"values": [{"userEnteredValue": {"stringValue": h}} for h in ESTIMATE_TEMPLATE["headers"]]},
                    ],
                }],
            }],
        }).execute()

        sheet_id = spreadsheet["spreadsheetId"]
        sheet_url = spreadsheet["spreadsheetUrl"]
        logger.info(f"Google Sheet 생성 완료: {sheet_id}")

        # 컬럼 폭 설정
        requests = []
        for i, width in enumerate(ESTIMATE_TEMPLATE["column_widths"]):
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": 0,
                        "dimension": "COLUMNS",
                        "startIndex": i,
                        "endIndex": i + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            })

        # 헤더 스타일링
        requests.append({
            "repeatCell": {
                "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.31, "green": 0.27, "blue": 0.9},
                        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
            }
        })

        if requests:
            service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id, body={"requests": requests}
            ).execute()

        # DB에 문서로 저장
        doc = Document(
            project_id=project_id,
            user_id=user_id,
            document_type="estimate",
            title=title,
            status="uploaded",
            google_sheet_id=sheet_id,
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
            detail=json.dumps({"type": "google_sheet", "sheet_id": sheet_id}, ensure_ascii=False),
        ))
        await db.commit()

        return doc

    # ── 시트 연결 ──

    async def link_sheet(
        self, db: AsyncSession, project_id: int, user_id: int, sheet_url: str, title: str | None = None
    ) -> Document:
        """기존 Google Sheet URL 연결"""
        sheet_id = self._extract_sheet_id(sheet_url)
        if not sheet_id:
            raise ValueError("유효하지 않은 Google Sheets URL입니다")

        # 시트 접근 확인 및 제목 가져오기
        service = self._get_service()
        try:
            spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
            sheet_title = title or spreadsheet["properties"]["title"]
        except Exception as e:
            logger.error(f"Google Sheet 접근 실패: {e}")
            raise ValueError("Google Sheet에 접근할 수 없습니다. URL과 권한을 확인해 주세요.")

        # DB 저장
        doc = Document(
            project_id=project_id,
            user_id=user_id,
            document_type="estimate",
            title=sheet_title,
            status="uploaded",
            google_sheet_id=sheet_id,
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
            target_name=sheet_title,
            detail=json.dumps({"type": "google_sheet_link", "sheet_id": sheet_id}, ensure_ascii=False),
        ))
        await db.commit()

        return doc

    # ── 시트 내용 읽기 ──

    async def read_sheet_data(self, document_id: int, db: AsyncSession) -> dict:
        """Google Sheet 내용 읽기"""
        doc = await db.get(Document, document_id)
        if not doc or not doc.google_sheet_id:
            raise ValueError("Google Sheet가 연결되지 않은 문서입니다")

        service = self._get_service()
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=doc.google_sheet_id,
                range="A1:Z1000",
            ).execute()

            values = result.get("values", [])
            return {
                "sheet_id": doc.google_sheet_id,
                "title": doc.title,
                "headers": values[0] if values else [],
                "rows": values[1:] if len(values) > 1 else [],
                "total_rows": len(values) - 1 if values else 0,
            }
        except Exception as e:
            logger.error(f"Google Sheet 읽기 실패: {e}")
            raise ValueError(f"시트 데이터를 읽을 수 없습니다: {e}")

    # ── AI 파싱 ──

    async def parse_sheet_with_ai(self, document_id: int, db: AsyncSession) -> dict:
        """Google Sheet 내용을 AI로 파싱하여 견적 항목 구조화"""
        sheet_data = await self.read_sheet_data(document_id, db)

        if not sheet_data["rows"]:
            raise ValueError("시트에 데이터가 없습니다")

        # 시트 내용을 텍스트로 변환
        headers = sheet_data["headers"]
        text_lines = [" | ".join(headers)]
        text_lines.append("-" * 50)
        for row in sheet_data["rows"]:
            # 컬럼 수 맞추기
            padded = row + [""] * (len(headers) - len(row))
            text_lines.append(" | ".join(padded[:len(headers)]))
        sheet_text = "\n".join(text_lines)

        # AI 분석
        from google.genai import types

        prompt = """당신은 한국어 견적서 분석 전문가입니다.
다음 견적서 테이블에서 항목을 추출해 주세요.

아래 JSON 형식으로 응답:
{
    "estimate_items": [
        {
            "name": "항목명",
            "quantity": 수량(숫자),
            "unit": "단위",
            "unit_price": 단가(숫자),
            "amount": 금액(숫자),
            "estimated_days": 예상일수(숫자) 또는 null
        }
    ],
    "total_amount": 총액(숫자),
    "estimated_duration_days": 총 예상 기간(일) 또는 null
}"""

        gemini = GeminiService()
        response = await gemini.client.aio.models.generate_content(
            model=gemini.model,
            contents=f"{prompt}\n\n---\n{sheet_text[:12000]}\n---",
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                http_options=types.HttpOptions(timeout=120_000),
            ),
        )
        result = gemini._parse_json_response(response.text)

        # 문서 ai_analysis에 저장
        doc = await db.get(Document, document_id)
        if doc:
            doc.ai_analysis = result
            doc.status = "review_pending"
            await db.commit()

        return result

    # ── 유틸리티 ──

    @staticmethod
    def _extract_sheet_id(url: str) -> str | None:
        """Google Sheets URL에서 spreadsheet ID 추출"""
        patterns = [
            r"/spreadsheets/d/([a-zA-Z0-9-_]+)",
            r"^([a-zA-Z0-9-_]{20,})$",  # ID 직접 입력
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
