import json
import logging
from openai import AsyncOpenAI
from app.config import settings
from app.schemas.schedule import ContractSchedule, TaskItem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OpenAIService:
    """OpenAI API 연동 서비스"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def extract_schedule(self, contract_text: str) -> tuple[ContractSchedule, list[TaskItem]]:
        """계약서 텍스트에서 일정 정보와 업무 목록 추출"""

        system_prompt = """당신은 한국어 외주용역 계약서 분석 전문가입니다.
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
- "착수일로부터 N일 이내" → 상대적 표현으로 기록

반드시 아래 JSON 형식으로 응답하세요."""

        user_prompt = f"""다음 외주용역 계약서에서 추진 일정 정보를 추출하고 업무 목록을 생성해 주세요:

---
{contract_text[:12000]}
---

아래 JSON 형식으로 응답해 주세요:
{{
    "contract_schedule": {{
        "contract_name": "계약명",
        "contract_start_date": "YYYY-MM-DD 또는 원문",
        "contract_end_date": "YYYY-MM-DD 또는 원문",
        "total_duration_days": 숫자 또는 null,
        "schedules": [
            {{
                "phase": "단계명",
                "schedule_type": "착수/설계/개발/테스트/납품/중간보고/최종보고/검수/인도/기타",
                "start_date": "YYYY-MM-DD 또는 null",
                "end_date": "YYYY-MM-DD 또는 null",
                "description": "설명",
                "deliverables": ["산출물1", "산출물2"]
            }}
        ],
        "milestones": ["마일스톤1", "마일스톤2"]
    }},
    "task_list": [
        {{
            "task_id": 1,
            "task_name": "업무명",
            "phase": "해당 단계",
            "due_date": "YYYY-MM-DD 또는 null",
            "priority": "긴급/높음/보통/낮음",
            "status": "대기"
        }}
    ]
}}"""

        # 추출된 텍스트 로깅
        logger.info(f"추출된 텍스트 길이: {len(contract_text)} 자")
        logger.info(f"텍스트 미리보기: {contract_text[:500]}")

        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",  # 비용 절감을 위해 mini 모델 사용
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        result_text = response.choices[0].message.content
        logger.info(f"OpenAI 응답: {result_text[:1000]}")

        result = json.loads(result_text)

        # ContractSchedule 파싱
        schedule_data = result.get("contract_schedule", {})
        logger.info(f"파싱된 일정 데이터: {schedule_data}")
        contract_schedule = ContractSchedule(**schedule_data)

        # TaskItem 리스트 파싱
        task_data = result.get("task_list", [])
        logger.info(f"파싱된 업무 목록: {len(task_data)}개")
        task_list = [TaskItem(**task) for task in task_data]

        return contract_schedule, task_list
