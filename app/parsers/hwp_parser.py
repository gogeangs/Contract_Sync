import zipfile
import zlib
import struct
from pathlib import Path
from xml.etree import ElementTree as ET

import olefile

from app.parsers.base import BaseParser, ParseResult


class HWPParser(BaseParser):
    """HWP 파일 파서 (한글 문서)"""

    async def parse(self, file_path: str) -> ParseResult:
        """HWP에서 텍스트 추출 - 여러 방법 시도"""

        # 방법 1: HWPX 형식 (ZIP 기반, 한글 2010+ 신형식)
        if self._is_hwpx(file_path):
            text = await self._parse_hwpx(file_path)
            return ParseResult(text=text)

        # 방법 2: OLE 기반 HWP 파싱
        try:
            text = await self._parse_hwp_ole(file_path)
            return ParseResult(text=text)
        except Exception as e:
            raise ValueError(f"HWP 파싱 실패: {str(e)}")

    def _is_hwpx(self, file_path: str) -> bool:
        """HWPX 형식인지 확인 (ZIP 시그니처)"""
        try:
            with open(file_path, "rb") as f:
                header = f.read(4)
                return header == b"PK\x03\x04"  # ZIP 시그니처
        except Exception:
            return False

    async def _parse_hwpx(self, file_path: str) -> str:
        """HWPX (XML 기반) 파싱"""
        text_content = []

        with zipfile.ZipFile(file_path, "r") as zf:
            # Contents/ 폴더 내 section XML 파일들 읽기
            for name in sorted(zf.namelist()):
                if name.startswith("Contents/section") and name.endswith(".xml"):
                    with zf.open(name) as f:
                        content = f.read().decode("utf-8")
                        text = self._extract_text_from_xml(content)
                        if text.strip():
                            text_content.append(text)

        return "\n\n".join(text_content)

    def _extract_text_from_xml(self, xml_content: str) -> str:
        """XML에서 텍스트 추출"""
        text_parts = []
        try:
            # 네임스페이스 제거하고 파싱
            xml_content = self._remove_namespaces(xml_content)
            root = ET.fromstring(xml_content)

            # 텍스트 노드 찾기
            for elem in root.iter():
                if elem.text and elem.text.strip():
                    text_parts.append(elem.text.strip())
                if elem.tail and elem.tail.strip():
                    text_parts.append(elem.tail.strip())
        except ET.ParseError:
            pass

        return " ".join(text_parts)

    def _remove_namespaces(self, xml_content: str) -> str:
        """XML 네임스페이스 제거"""
        import re

        # xmlns 속성 제거
        xml_content = re.sub(r'\sxmlns[^"]*"[^"]*"', "", xml_content)
        # 태그의 네임스페이스 접두사 제거
        xml_content = re.sub(r"<(/?)[\w]+:", r"<\1", xml_content)
        return xml_content

    async def _parse_hwp_ole(self, file_path: str) -> str:
        """OLE 기반 HWP 파싱"""
        if not olefile.isOleFile(file_path):
            raise ValueError("유효한 HWP 파일이 아닙니다.")

        # M-14: context manager 패턴으로 리소스 누수 방지
        text_content = []
        with olefile.OleFileIO(file_path) as ole:
            # 파일 헤더 확인
            if not ole.exists("FileHeader"):
                raise ValueError("HWP 파일 헤더를 찾을 수 없습니다.")

            header_stream = ole.openstream("FileHeader")
            header = header_stream.read()
            header_stream.close()
            is_compressed = header[36] & 1  # 압축 여부

            # BodyText 스트림 읽기
            section_num = 0
            while ole.exists(f"BodyText/Section{section_num}"):
                stream = ole.openstream(f"BodyText/Section{section_num}")
                data = stream.read()
                stream.close()

                if is_compressed:
                    try:
                        data = zlib.decompress(data, -15)
                    except zlib.error:
                        pass

                text = self._extract_text_from_bodytext(data)
                if text.strip():
                    text_content.append(text)

                section_num += 1

        return "\n\n".join(text_content)

    def _extract_text_from_bodytext(self, data: bytes) -> str:
        """BodyText 바이너리에서 텍스트 추출"""
        text = []
        i = 0

        while i < len(data) - 1:
            try:
                char_code = struct.unpack("<H", data[i : i + 2])[0]

                # 일반 문자 범위 (ASCII + 한글)
                if 0x20 <= char_code < 0xD800 or 0xAC00 <= char_code <= 0xD7A3:
                    text.append(chr(char_code))
                elif char_code == 0x0D or char_code == 0x0A:  # 줄바꿈
                    text.append("\n")
                elif char_code == 0x09:  # 탭
                    text.append("\t")
            except (struct.error, ValueError):
                pass
            i += 2

        return "".join(text)
