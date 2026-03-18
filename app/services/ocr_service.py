"""사업자등록증 OCR 서비스 — 2차 개발

Gemini Vision API로 사업자등록증/증명원에서 정보를 추출한다.
"""
import asyncio
import json
import logging
from functools import partial

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 2

OCR_PROMPT = """이 이미지는 사업자등록증 또는 사업자등록증명원입니다.
아래 항목을 JSON으로 추출하세요. 인식할 수 없는 항목은 null로 입력하세요.

{
  "business_number": "사업자등록번호 (000-00-00000 형식)",
  "name": "상호 또는 법인명",
  "representative": "대표자명",
  "business_type": "업태",
  "business_category": "종목",
  "address": "사업장 소재지",
  "phone": "전화번호",
  "corp_number": "법인등록번호 (없으면 null)"
}"""


class OCRService:
    """Gemini Vision 기반 사업자등록증 OCR"""

    def __init__(self):
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = "gemini-2.0-flash"

    async def extract_business_info(
        self, file_bytes: bytes, mime_type: str
    ) -> dict | None:
        """사업자등록증에서 정보를 추출하여 dict로 반환. 실패 시 None."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                image_part = types.Part.from_bytes(
                    data=file_bytes, mime_type=mime_type
                )
                config = types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                )

                # 동기 Gemini SDK를 이벤트 루프 블로킹 없이 실행
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    partial(
                        self.client.models.generate_content,
                        model=self.model,
                        contents=[
                            types.Content(
                                role="user",
                                parts=[image_part, types.Part(text=OCR_PROMPT)],
                            )
                        ],
                        config=config,
                    ),
                )

                if not response.text:
                    logger.warning(f"OCR 응답 비어 있음 (attempt {attempt + 1})")
                    continue

                result = json.loads(response.text)

                # 필수 필드 검증
                if not result.get("business_number") and not result.get("name"):
                    logger.warning(f"OCR 필수 필드 누락 (attempt {attempt + 1})")
                    continue

                return result

            except json.JSONDecodeError:
                logger.warning(f"OCR JSON 파싱 실패 (attempt {attempt + 1})")
            except Exception as e:
                logger.error(f"OCR Gemini 호출 실패 (attempt {attempt + 1}): {e}")

        return None


# 싱글턴 인스턴스
_ocr_instance: OCRService | None = None


def get_ocr_service() -> OCRService:
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = OCRService()
    return _ocr_instance
