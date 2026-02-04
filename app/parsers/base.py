from abc import ABC, abstractmethod


class BaseParser(ABC):
    """파일 파서 추상 클래스"""

    @abstractmethod
    async def parse(self, file_path: str) -> str:
        """파일에서 텍스트를 추출합니다."""
        pass
