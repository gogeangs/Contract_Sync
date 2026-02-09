import json
import logging
import google.generativeai as genai
from app.config import settings
from app.schemas.schedule import ContractSchedule, TaskItem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GeminiService:
    """Google Gemini API 연동 서비스"""

    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

    async def extract_schedule(
        self,
        text: str = "",
        images: list[bytes] | None = None,
    ) -> tuple[ContractSchedule, list[TaskItem], str]:
        """계약서에서 일정 정보와 업무 목록 추출 (텍스트 또는 이미지)

        Returns:
            tuple: (contract_schedule, task_list, raw_text)
        """

        system_prompt = self._build_system_prompt()

        if images:
            result_text = await self._extract_from_images(
                system_prompt, images, supplementary_text=text
            )
        else:
            result_text = await self._extract_from_text(system_prompt, text)

        logger.info(f"Gemini 응답: {result_text[:1000]}")
        result = json.loads(result_text)

        # ContractSchedule 파싱
        schedule_data = result.get("contract_schedule", {})
        logger.info(f"파싱된 일정 데이터: {schedule_data}")
        contract_schedule = ContractSchedule(**schedule_data)

        # TaskItem 리스트 파싱
        task_data = result.get("task_list", [])
        logger.info(f"파싱된 업무 목록: {len(task_data)}개")
        task_list = [TaskItem(**task) for task in task_data]

        # 원문 텍스트 (이미지 기반 추출 시 Gemini가 OCR한 텍스트)
        extracted_text = result.get("raw_text", "")

        return contract_schedule, task_list, extracted_text

    async def _extract_from_text(self, system_prompt: str, text: str) -> str:
        """텍스트 기반 추출 (DOCX, HWP, 텍스트 PDF)"""
        logger.info(f"텍스트 기반 추출: {len(text)}자")

        user_prompt = f"""다음 외주용역 계약서에서 추진 일정 정보를 추출하고 업무 목록을 생성해 주세요:

---
{text[:12000]}
---

{self._build_json_format()}"""

        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        response = await self.model.generate_content_async(full_prompt)
        return response.text

    async def _extract_from_images(
        self,
        system_prompt: str,
        images: list[bytes],
        supplementary_text: str = "",
    ) -> str:
        """이미지 기반 추출 (스캔 PDF) - Gemini 멀티모달"""
        logger.info(f"이미지 기반 추출: {len(images)}페이지")

        parts = [
            system_prompt + "\n\n",
            "다음은 외주용역 계약서의 각 페이지 이미지입니다. "
            "모든 페이지를 분석하여 추진 일정 정보를 추출하고 "
            "업무 목록을 생성해 주세요.\n\n",
        ]

        # 각 페이지 이미지 추가
        for i, img_bytes in enumerate(images):
            parts.append(f"--- 페이지 {i + 1} ---\n")
            parts.append({
                "mime_type": "image/png",
                "data": img_bytes,
            })

        # 보조 텍스트 추가
        if supplementary_text and supplementary_text.strip():
            parts.append(
                f"\n\n추가로 추출된 텍스트 (참고용):\n{supplementary_text[:4000]}"
            )

        parts.append(
            "\n\n중요: 이미지에 보이는 계약서의 전체 텍스트를 raw_text 필드에 그대로 옮겨 적어주세요.\n\n"
            + self._build_json_format()
        )

        response = await self.model.generate_content_async(parts)
        return response.text

    def _build_system_prompt(self) -> str:
        return """당신은 한국어 외주용역 계약서 분석 전문가입니다.
계약서 텍스트를 분석하여 추진 일정과 관련된 모든 정보를 체계적으로 추출해야 합니다.

다음 정보를 찾아 추출해 주세요:

1. **계약 기본 정보**
   - 계약명/사업명
   - 계약 착수일 (시작일)
   - 계약 완료일 (종료일)
   - 총 사업 기간

2. **단계별 추진 일정**
   각 단계에 대해 다음을 추출:
   - 단계명 (예: 1단계 설계, 2단계 개발)
   - 일정 유형: 착수, 완료, 설계, 개발, 테스트, 납품, 중간보고, 최종보고, 검수, 인도
   - 시작일/종료일
   - 산출물 목록

3. **주요 마일스톤**
   - 중간보고 일정
   - 최종보고 일정
   - 검수 일정
   - 인도 일정

4. **업무 목록 생성**
   추출된 일정을 기반으로 실행 가능한 업무 목록을 생성하세요.
   - 각 단계별 세부 업무
   - 마감일 설정
   - 우선순위 (긴급, 높음, 보통, 낮음)

한국어 날짜 표현 패턴을 인식해 주세요:
- "2024년 3월 15일" → "2024-03-15"
- "2024.03.15" → "2024-03-15"
- "착수일로부터 N일 이내" → 상대적 표현으로 기록"""

    def _build_json_format(self) -> str:
        return """아래 JSON 형식으로 응답해 주세요:
{
    "contract_schedule": {
        "contract_name": "계약명",
        "contract_start_date": "YYYY-MM-DD 또는 원문",
        "contract_end_date": "YYYY-MM-DD 또는 원문",
        "total_duration_days": 숫자 또는 null,
        "schedules": [
            {
                "phase": "단계명",
                "schedule_type": "착수/설계/개발/테스트/납품/중간보고/최종보고/검수/인도/기타",
                "start_date": "YYYY-MM-DD 또는 null",
                "end_date": "YYYY-MM-DD 또는 null",
                "description": "설명",
                "deliverables": ["산출물1", "산출물2"]
            }
        ],
        "milestones": ["마일스톤1", "마일스톤2"]
    },
    "task_list": [
        {
            "task_id": 1,
            "task_name": "업무명",
            "phase": "해당 단계",
            "due_date": "YYYY-MM-DD 또는 null",
            "priority": "긴급/높음/보통/낮음",
            "status": "대기"
        }
    ],
    "raw_text": "계약서 원문 전체 텍스트 (이미지인 경우 OCR하여 원문을 그대로 옮겨 적기, 텍스트인 경우 빈 문자열)"
}"""
