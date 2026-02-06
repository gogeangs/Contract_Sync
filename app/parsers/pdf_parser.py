import fitz  # PyMuPDF
import logging
import re
from app.parsers.base import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """PDF 파서 - 텍스트 추출 실패 시 이미지 렌더링 (Gemini 멀티모달용)"""

    TEXT_THRESHOLD = 100
    IMAGE_DPI_SCALE = 2.0  # 144 DPI
    MAX_IMAGE_PAGES = 20

    async def parse(self, file_path: str) -> ParseResult:
        text_pages = []
        has_empty_pages = False

        with fitz.open(file_path) as doc:
            logger.info(f"PDF 페이지 수: {len(doc)}")

            for page_num, page in enumerate(doc):
                page_text = self._extract_text_from_page(page)
                if page_text.strip():
                    text_pages.append(f"--- 페이지 {page_num + 1} ---\n{page_text}")
                else:
                    has_empty_pages = True

        total_text = "\n\n".join(text_pages)
        clean_text = total_text.replace("-", "").replace("페이지", "").strip()

        # 텍스트가 충분하면 텍스트만 반환
        if len(clean_text) >= self.TEXT_THRESHOLD and not has_empty_pages:
            return ParseResult(text=total_text)

        # 텍스트 부족 또는 스캔 페이지 → 이미지로 렌더링
        logger.info(f"텍스트 부족({len(clean_text)}자) 또는 스캔 페이지 감지. "
                     f"Gemini 멀티모달용 이미지 렌더링 시작.")
        images = self._render_pages_as_images(file_path)

        return ParseResult(text=total_text if text_pages else "", images=images)

    def _extract_text_from_page(self, page) -> str:
        text = page.get_text("text")
        return self._filter_image_metadata(text)

    def _filter_image_metadata(self, text: str) -> str:
        if not text:
            return ""
        filtered = re.sub(r'<image:[^>]*>', '', text)
        filtered = re.sub(r'\n\s*\n', '\n', filtered)
        return filtered.strip()

    def _render_pages_as_images(self, file_path: str) -> list[bytes]:
        """PDF 페이지를 PNG 이미지로 렌더링"""
        images = []
        with fitz.open(file_path) as doc:
            page_count = min(len(doc), self.MAX_IMAGE_PAGES)
            for page_num in range(page_count):
                page = doc[page_num]
                mat = fitz.Matrix(self.IMAGE_DPI_SCALE, self.IMAGE_DPI_SCALE)
                pix = page.get_pixmap(matrix=mat)
                png_bytes = pix.tobytes("png")
                images.append(png_bytes)
                logger.info(f"이미지 렌더링: 페이지 {page_num + 1}/{page_count} "
                           f"({len(png_bytes)} bytes)")
        return images
