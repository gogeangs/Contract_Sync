import fitz  # PyMuPDF
import logging
import re
from app.parsers.base import BaseParser

logger = logging.getLogger(__name__)

# EasyOCR 리더를 전역으로 초기화 (한 번만 로드)
_ocr_reader = None


def get_ocr_reader():
    """EasyOCR 리더 싱글톤 (한국어 지원)"""
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            logger.info("EasyOCR 초기화 중... (한국어 모델)")
            _ocr_reader = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
            logger.info("EasyOCR 초기화 완료")
        except Exception as e:
            logger.error(f"EasyOCR 초기화 실패: {e}")
            _ocr_reader = None
    return _ocr_reader


class PDFParser(BaseParser):
    """PDF 파일 파서 (EasyOCR 한국어 지원)"""

    async def parse(self, file_path: str) -> str:
        """PDF에서 텍스트 추출 - 텍스트 추출 실패 시 OCR 사용"""
        text_content = []
        needs_ocr = False

        with fitz.open(file_path) as doc:
            logger.info(f"PDF 페이지 수: {len(doc)}")

            for page_num, page in enumerate(doc):
                page_text = self._extract_text_from_page(page)

                if page_text.strip():
                    text_content.append(f"--- 페이지 {page_num + 1} ---\n{page_text}")
                else:
                    needs_ocr = True

        total_text = "\n\n".join(text_content)
        clean_text = total_text.replace("-", "").replace("페이지", "").strip()

        if len(clean_text) < 100 or needs_ocr:
            logger.info("텍스트가 부족합니다. EasyOCR을 시도합니다...")
            ocr_text = await self._ocr_pdf(file_path)
            if ocr_text:
                return ocr_text

        return total_text

    def _extract_text_from_page(self, page) -> str:
        """페이지에서 텍스트 추출"""
        text = page.get_text("text")
        return self._filter_image_metadata(text)

    def _filter_image_metadata(self, text: str) -> str:
        """이미지 메타데이터 필터링"""
        if not text:
            return ""
        filtered = re.sub(r'<image:[^>]*>', '', text)
        filtered = re.sub(r'\n\s*\n', '\n', filtered)
        return filtered.strip()

    async def _ocr_pdf(self, file_path: str, max_pages: int = 10) -> str:
        """EasyOCR로 PDF에서 텍스트 추출 (한국어 지원)"""
        reader = get_ocr_reader()
        if reader is None:
            return ""

        text_content = []

        try:
            with fitz.open(file_path) as doc:
                total_pages = min(len(doc), max_pages)
                logger.info(f"OCR 처리: {total_pages}페이지")

                for page_num in range(total_pages):
                    page = doc[page_num]
                    logger.info(f"OCR: 페이지 {page_num + 1}/{total_pages}")

                    # 72 DPI로 속도 향상
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
                    img_data = pix.tobytes("png")

                    # OCR 수행
                    results = reader.readtext(img_data, detail=1, paragraph=False)

                    page_texts = []
                    for item in results:
                        if len(item) >= 2:
                            text = item[1]
                            conf = item[2] if len(item) > 2 else 0.5
                            if conf > 0.3 and text.strip():
                                page_texts.append(text)

                    if page_texts:
                        text_content.append(f"--- 페이지 {page_num + 1} (OCR) ---\n" + "\n".join(page_texts))

            result = "\n\n".join(text_content)
            logger.info(f"OCR 결과: {len(result)} 자")
            return result

        except Exception as e:
            logger.error(f"OCR 오류: {e}")
            return ""
