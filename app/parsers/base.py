from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParseResult:
    """파서 출력 - 텍스트 또는 이미지(스캔 PDF용)"""
    text: str = ""
    images: list[bytes] = field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return bool(self.text and self.text.strip())

    @property
    def has_images(self) -> bool:
        return bool(self.images)


class BaseParser(ABC):
    """파일 파서 추상 클래스"""

    @abstractmethod
    async def parse(self, file_path: str) -> ParseResult:
        """파일에서 텍스트/이미지를 추출합니다."""
        pass
