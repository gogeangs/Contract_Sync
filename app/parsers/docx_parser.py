from docx import Document
from app.parsers.base import BaseParser


class DocxParser(BaseParser):
    """DOCX 파일 파서"""

    async def parse(self, file_path: str) -> str:
        """DOCX에서 텍스트 추출"""
        doc = Document(file_path)
        text_content = []

        # 문단 추출
        for para in doc.paragraphs:
            if para.text.strip():
                text_content.append(para.text)

        # 표 추출 (일정표 추출에 중요)
        for table in doc.tables:
            table_text = self._extract_table(table)
            if table_text.strip():
                text_content.append(f"\n[표]\n{table_text}")

        return "\n\n".join(text_content)

    def _extract_table(self, table) -> str:
        """표에서 텍스트 추출"""
        result = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            # 중복 셀 제거 (병합된 셀 처리)
            unique_cells = []
            prev = None
            for cell in cells:
                if cell != prev:
                    unique_cells.append(cell)
                    prev = cell
            result.append(" | ".join(unique_cells))
        return "\n".join(result)
