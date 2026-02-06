from app.parsers.base import BaseParser, ParseResult
from app.parsers.pdf_parser import PDFParser
from app.parsers.docx_parser import DocxParser
from app.parsers.hwp_parser import HWPParser


class ParserFactory:
    """파일 확장자에 따른 파서 생성"""

    _parsers = {
        ".pdf": PDFParser,
        ".docx": DocxParser,
        ".doc": DocxParser,
        ".hwp": HWPParser,
        ".hwpx": HWPParser,
    }

    @classmethod
    def get_parser(cls, file_extension: str) -> BaseParser:
        parser_class = cls._parsers.get(file_extension.lower())
        if not parser_class:
            raise ValueError(f"지원하지 않는 파일 형식: {file_extension}")
        return parser_class()

    @classmethod
    def get_supported_extensions(cls) -> list[str]:
        return list(cls._parsers.keys())
