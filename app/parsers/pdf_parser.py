import fitz  # PyMuPDF
import io
import logging
import re
from app.parsers.base import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """PDF 파서 - 텍스트 추출 실패 시 이미지 렌더링 (Gemini 멀티모달용)"""

    TEXT_THRESHOLD = 100
    # 텍스트 품질 판단: 페이지당 평균 글자 수 기준
    TEXT_QUALITY_THRESHOLD = 50
    IMAGE_DPI_SCALE = 2.0  # 144 DPI
    MAX_IMAGE_PAGES = 20
    # 개별 이미지 최대 크기 (바이트) - Gemini API 제한 대응
    MAX_IMAGE_BYTES_PER_PAGE = 4 * 1024 * 1024  # 4MB

    async def parse(self, file_path: str) -> ParseResult:
        text_pages = []
        page_count = 0
        empty_page_count = 0

        with fitz.open(file_path) as doc:
            page_count = len(doc)
            logger.info(f"PDF 페이지 수: {page_count}")

            for page_num, page in enumerate(doc):
                page_text = self._extract_text_from_page(page)
                if page_text.strip():
                    text_pages.append(f"--- 페이지 {page_num + 1} ---\n{page_text}")
                else:
                    empty_page_count += 1

        total_text = "\n\n".join(text_pages)
        # M-1: 하이픈 제거 대신 페이지 헤더/푸터 패턴만 제거 (날짜 보존)
        clean_text = re.sub(r'[-─━]+\s*페이지\s*\d*\s*[-─━]*', '', total_text).strip()

        # 스캔 PDF 판별: 텍스트 품질 기반
        is_scan = self._is_likely_scanned(clean_text, page_count, empty_page_count)

        # 텍스트가 충분하고 스캔이 아닌 경우 텍스트만 반환
        if len(clean_text) >= self.TEXT_THRESHOLD and not is_scan:
            logger.info(f"텍스트 기반 PDF: {len(clean_text)}자 추출 완료")
            return ParseResult(text=total_text)

        # 스캔 PDF → 이미지로 렌더링
        logger.info(f"스캔 PDF 감지 (텍스트: {len(clean_text)}자, "
                     f"빈 페이지: {empty_page_count}/{page_count}). "
                     f"Gemini 멀티모달용 이미지 렌더링 시작.")
        images = self._render_pages_as_images(file_path)

        return ParseResult(text=total_text if text_pages else "", images=images)

    def _is_likely_scanned(self, text: str, page_count: int, empty_page_count: int) -> bool:
        """텍스트 품질 기반 스캔 PDF 여부 판별"""
        if page_count == 0:
            return True

        # 빈 페이지가 하나라도 있으면 스캔 가능성 높음
        if empty_page_count > 0:
            return True

        # 페이지당 평균 글자 수가 기준 미만이면 스캔으로 판단
        avg_chars_per_page = len(text) / page_count
        if avg_chars_per_page < self.TEXT_QUALITY_THRESHOLD:
            logger.info(f"페이지당 평균 {avg_chars_per_page:.0f}자 - 스캔 PDF로 판단")
            return True

        # 한국어/영문 비율이 극히 낮으면 OCR 노이즈일 가능성
        meaningful_chars = len(re.findall(r'[가-힣a-zA-Z0-9]', text))
        if len(text) > 0 and meaningful_chars / len(text) < 0.3:
            logger.info(f"의미 있는 문자 비율 {meaningful_chars/len(text):.1%} - 스캔 PDF로 판단")
            return True

        return False

    def _extract_text_from_page(self, page) -> str:
        text = page.get_text("text")
        return self._filter_image_metadata(text)

    def _filter_image_metadata(self, text: str) -> str:
        if not text:
            return ""
        filtered = re.sub(r'<image:[^>]*>', '', text)
        filtered = re.sub(r'\n\s*\n', '\n', filtered)
        return filtered.strip()

    MAX_TOTAL_IMAGE_BYTES = 18 * 1024 * 1024  # 18MB 총 이미지 제한 (Gemini API 대응)

    def _render_pages_as_images(self, file_path: str) -> list[bytes]:
        """PDF 페이지를 PNG 이미지로 렌더링 (Gemini API 제한에 맞게 최적화)"""
        images = []
        total_bytes = 0
        with fitz.open(file_path) as doc:
            page_count = min(len(doc), self.MAX_IMAGE_PAGES)
            for page_num in range(page_count):
                try:
                    page = doc[page_num]
                    png_bytes = self._render_page_optimized(page)
                    if png_bytes is None:
                        logger.warning(f"페이지 {page_num + 1} 렌더링 건너뜀 (최적화 실패)")
                        continue
                    total_bytes += len(png_bytes)
                    if total_bytes > self.MAX_TOTAL_IMAGE_BYTES:
                        logger.warning(f"총 이미지 크기 제한 초과 ({total_bytes} bytes). "
                                       f"{page_num}페이지까지 처리.")
                        break
                    images.append(png_bytes)
                    logger.info(f"이미지 렌더링: 페이지 {page_num + 1}/{page_count} "
                               f"({len(png_bytes):,} bytes)")
                except Exception as e:
                    logger.warning(f"페이지 {page_num + 1} 렌더링 실패: {e}")
                    continue

        if not images:
            logger.error("이미지 렌더링 결과가 없습니다.")
        else:
            logger.info(f"이미지 렌더링 완료: {len(images)}페이지, "
                       f"총 {total_bytes:,} bytes")
        return images

    def _render_page_optimized(self, page) -> bytes | None:
        """단일 페이지를 최적화된 크기로 렌더링"""
        # 1차: 기본 DPI로 렌더링
        scale = self.IMAGE_DPI_SCALE
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")

        # 이미지가 페이지당 제한 이내면 바로 반환
        if len(png_bytes) <= self.MAX_IMAGE_BYTES_PER_PAGE:
            return png_bytes

        # 2차: DPI를 낮춰서 재렌더링
        for reduced_scale in [1.5, 1.0]:
            logger.info(f"이미지 크기 초과 ({len(png_bytes):,} bytes), "
                       f"DPI 축소: scale={reduced_scale}")
            mat = fitz.Matrix(reduced_scale, reduced_scale)
            pix = page.get_pixmap(matrix=mat)
            png_bytes = pix.tobytes("png")
            if len(png_bytes) <= self.MAX_IMAGE_BYTES_PER_PAGE:
                return png_bytes

        # 최소 DPI에서도 초과하면 그래도 반환 (Gemini가 처리 시도)
        logger.warning(f"최소 DPI에서도 이미지 크기 초과: {len(png_bytes):,} bytes")
        return png_bytes
