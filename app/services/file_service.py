import uuid
import aiofiles
from pathlib import Path
from fastapi import UploadFile

from app.config import settings
from app.parsers import ParserFactory


class FileService:
    """파일 처리 서비스"""

    def __init__(self):
        self.upload_dir = Path(settings.upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size = settings.max_file_size_mb * 1024 * 1024

    async def save_upload_file(self, file: UploadFile) -> Path:
        """업로드된 파일을 임시 저장"""
        # 파일 확장자 추출
        original_name = file.filename or "unknown"
        extension = Path(original_name).suffix.lower()

        # 지원하는 확장자인지 확인
        supported = ParserFactory.get_supported_extensions()
        if extension not in supported:
            raise ValueError(f"지원하지 않는 파일 형식입니다. 지원 형식: {', '.join(supported)}")

        # 고유 파일명 생성
        unique_name = f"{uuid.uuid4()}{extension}"
        file_path = self.upload_dir / unique_name

        # 파일 저장 (청크 단위)
        total_size = 0
        async with aiofiles.open(file_path, "wb") as f:
            while chunk := await file.read(8192):
                total_size += len(chunk)
                if total_size > self.max_file_size:
                    await f.close()
                    file_path.unlink(missing_ok=True)
                    raise ValueError(f"파일 크기가 {settings.max_file_size_mb}MB를 초과합니다.")
                await f.write(chunk)

        return file_path

    async def parse_file(self, file_path: Path) -> str:
        """파일을 파싱하여 텍스트 추출"""
        extension = file_path.suffix.lower()
        parser = ParserFactory.get_parser(extension)
        return await parser.parse(str(file_path))

    async def cleanup(self, file_path: Path) -> None:
        """임시 파일 삭제"""
        try:
            if file_path.exists():
                file_path.unlink()
        except Exception:
            pass
