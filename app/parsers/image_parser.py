import logging
from pathlib import Path
from app.parsers.base import BaseParser, ParseResult

logger = logging.getLogger(__name__)

# 이미지 최대 크기 (4MB)
MAX_IMAGE_SIZE = 4 * 1024 * 1024


class ImageParser(BaseParser):
    """이미지 파서 - 스캔 이미지를 Gemini 멀티모달로 직접 전달"""

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}

    async def parse(self, file_path: str) -> ParseResult:
        path = Path(file_path)
        ext = path.suffix.lower()

        # MIME 타입 결정
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".tiff": "image/tiff",
            ".tif": "image/tiff", ".bmp": "image/bmp",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(ext, "image/png")

        img_bytes = path.read_bytes()
        logger.info(f"이미지 파일 로드: {path.name} ({len(img_bytes):,} bytes, {mime_type})")

        # PNG가 아닌 경우 Gemini 호환을 위해 PNG로 변환 시도
        if ext not in (".png",):
            try:
                img_bytes = self._convert_to_png(img_bytes)
                logger.info(f"PNG 변환 완료: {len(img_bytes):,} bytes")
            except Exception as e:
                logger.warning(f"PNG 변환 실패, 원본 사용: {e}")

        # 크기 제한 확인
        if len(img_bytes) > MAX_IMAGE_SIZE:
            img_bytes = self._resize_image(img_bytes)

        return ParseResult(text="", images=[img_bytes])

    def _convert_to_png(self, img_bytes: bytes) -> bytes:
        """이미지를 PNG로 변환"""
        from io import BytesIO
        from PIL import Image

        with Image.open(BytesIO(img_bytes)) as img:
            if img.mode in ("RGBA", "LA"):
                pass
            elif img.mode != "RGB":
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

    def _resize_image(self, img_bytes: bytes) -> bytes:
        """이미지를 Gemini API 제한에 맞게 리사이즈"""
        from io import BytesIO
        from PIL import Image

        with Image.open(BytesIO(img_bytes)) as img:
            # 최대 2048px 기준으로 비율 축소
            max_dim = 2048
            ratio = min(max_dim / img.width, max_dim / img.height, 1.0)
            if ratio < 1.0:
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)
                logger.info(f"이미지 리사이즈: {new_size}")

            buf = BytesIO()
            img.save(buf, format="PNG")
            result = buf.getvalue()
            logger.info(f"리사이즈 후 크기: {len(result):,} bytes")
            return result
