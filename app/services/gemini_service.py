import json
import logging
import re
from google import genai
from google.genai import types
from app.config import settings
from app.schemas.schedule import ContractSchedule, TaskItem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_RETRIES = 2


class GeminiService:
    """Google Gemini API 연동 서비스"""

    def __init__(self):
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = "gemini-2.0-flash"
        self.config = types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
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
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                if images:
                    result_text = await self._extract_from_images(
                        system_prompt, images, supplementary_text=text
                    )
                else:
                    result_text = await self._extract_from_text(system_prompt, text)

                # M-12: 민감 데이터 로깅 방지 (계약 금액, 내용 등 제외)
                logger.info(f"Gemini 응답 수신 (시도 {attempt + 1}, 길이: {len(result_text)}자)")
                result = self._parse_json_response(result_text)

                # ContractSchedule 파싱
                schedule_data = result.get("contract_schedule", {})
                logger.info(f"일정 데이터 파싱 완료: {len(schedule_data.get('schedules', []))}개 일정")
                contract_schedule = ContractSchedule(**schedule_data)

                # TaskItem 리스트 파싱
                task_data = result.get("task_list", [])
                logger.info(f"업무 목록 파싱 완료: {len(task_data)}개")
                task_list = [TaskItem(**task) for task in task_data]

                # 원문 텍스트 (이미지 기반 추출 시 Gemini가 OCR한 텍스트)
                extracted_text = result.get("raw_text", "")

                return contract_schedule, task_list, extracted_text

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                last_error = e
                logger.warning(f"Gemini 응답 파싱 실패 (시도 {attempt + 1}/{MAX_RETRIES + 1}): {e}")
                if attempt < MAX_RETRIES:
                    continue
            except Exception as e:
                last_error = e
                logger.error(f"Gemini API 호출 실패: {e}")
                break

        raise RuntimeError(f"계약서 분석에 실패했습니다: {last_error}")

    def _parse_json_response(self, text: str) -> dict:
        """Gemini 응답에서 JSON을 안전하게 파싱"""
        # 직접 파싱 시도
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # markdown 코드 블록에서 JSON 추출 시도
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1).strip())

        raise json.JSONDecodeError("Gemini 응답에서 유효한 JSON을 찾을 수 없습니다", text, 0)

    async def _extract_from_text(self, system_prompt: str, text: str) -> str:
        """텍스트 기반 추출 (DOCX, HWP, 텍스트 PDF)"""
        logger.info(f"텍스트 기반 추출: {len(text)}자")

        user_prompt = f"""다음 외주용역 계약서에서 추진 일정 정보를 추출하고 업무 목록을 생성해 주세요:

---
{text[:12000]}
---

{self._build_json_format()}"""

        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=self.config.temperature,
                    response_mime_type=self.config.response_mime_type,
                    http_options=types.HttpOptions(timeout=120_000),
                ),
            )
            return response.text
        except Exception as e:
            logger.error(f"Gemini API 텍스트 추출 실패: {type(e).__name__}: {e}")
            raise

    async def _extract_from_images(
        self,
        system_prompt: str,
        images: list[bytes],
        supplementary_text: str = "",
    ) -> str:
        """이미지 기반 추출 (스캔 PDF) - Gemini 멀티모달"""
        total_size = sum(len(img) for img in images)
        logger.info(f"이미지 기반 추출: {len(images)}페이지, "
                    f"총 {total_size:,} bytes")

        parts = [
            types.Part.from_text(
                system_prompt + "\n\n"
                "다음은 외주용역 계약서의 각 페이지 이미지입니다. "
                "모든 페이지를 분석하여 추진 일정 정보를 추출하고 "
                "업무 목록을 생성해 주세요.\n\n"
            ),
        ]

        # 각 페이지 이미지 추가
        for i, img_bytes in enumerate(images):
            parts.append(types.Part.from_text(f"--- 페이지 {i + 1} ---\n"))
            parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))

        # 보조 텍스트 추가
        if supplementary_text and supplementary_text.strip():
            parts.append(types.Part.from_text(
                f"\n\n추가로 추출된 텍스트 (참고용):\n{supplementary_text[:4000]}"
            ))

        parts.append(types.Part.from_text(
            "\n\n중요: 이미지에 보이는 계약서의 전체 텍스트를 raw_text 필드에 그대로 옮겨 적어주세요.\n\n"
            + self._build_json_format()
        ))

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=types.Content(parts=parts),
                config=types.GenerateContentConfig(
                    temperature=self.config.temperature,
                    response_mime_type=self.config.response_mime_type,
                    http_options=types.HttpOptions(timeout=180_000),
                ),
            )
            if not response.text:
                raise RuntimeError("Gemini가 빈 응답을 반환했습니다. 이미지 품질을 확인해 주세요.")
            return response.text
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Gemini API 이미지 추출 실패: {type(e).__name__}: {error_msg}")
            # 이미지 크기 관련 에러인 경우 구체적 안내
            if "too large" in error_msg.lower() or "payload" in error_msg.lower():
                raise RuntimeError(
                    f"스캔 이미지 크기가 너무 큽니다 ({total_size // 1024 // 1024}MB). "
                    f"더 낮은 해상도로 스캔하거나 페이지 수를 줄여주세요."
                )
            raise

    async def generate_completion_draft(self, context: dict) -> dict:
        """완료 보고 초안 생성 (제목 + 본문)"""

        system_prompt = """당신은 프로젝트 업무 완료 보고를 작성하는 비즈니스 커뮤니케이션 전문가입니다.
발주처 담당자에게 보내는 업무 완료 이메일의 제목과 본문을 작성해 주세요.

작성 원칙:
1. 정중하고 간결한 비즈니스 어투 사용 (존칭: ~합니다)
2. 불필요한 인사말이나 미사여구 최소화
3. 핵심 내용을 먼저, 부가 설명은 후에
4. 첨부 산출물이 있으면 확인을 요청하는 문구 포함
5. 본문은 300자 이내로 간결하게

주의:
- 발주처 담당자의 이름은 알 수 없으므로 "담당자님" 사용 금지
- "안녕하세요," 로 시작
- "감사합니다." 로 마무리
- HTML 태그 사용하지 않음 (순수 텍스트)

반드시 아래 JSON 형식으로 응답하세요:
{"subject": "이메일 제목", "body": "이메일 본문"}"""

        user_prompt = (
            "다음 정보를 기반으로 완료 보고 이메일 초안을 작성해 주세요:\n\n"
            f"- 프로젝트명: {context.get('project_name', '')}\n"
            f"- 업무명: {context.get('task_name', '')}\n"
            f"- 발주처: {context.get('client_name', '발주처')}\n"
            f"- 발신자: {context.get('sender_name', '')}\n"
            f"- 완료일: {context.get('completed_at', '')}\n"
            f"- 처리 내용: {context.get('note', '없음')}\n"
        )

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.3,
                    response_mime_type="application/json",
                    http_options=types.HttpOptions(timeout=60_000),
                ),
            )
            result = self._parse_json_response(response.text)
            subject = result.get("subject", "")
            body = result.get("body", "")
            if not subject or not body:
                raise RuntimeError("AI가 유효한 초안을 생성하지 못했습니다")
            return {"subject": subject, "body": body}
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"AI 완료 보고 초안 파싱 실패: {e}")
            raise RuntimeError("AI 초안 생성에 실패했습니다")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"AI 완료 보고 초안 생성 실패: {e}")
            raise RuntimeError(f"AI 초안 생성에 실패했습니다: {e}")

    async def generate_periodic_report(self, context: dict) -> dict:
        """정기 보고서 생성 (title + content_html + content_json)"""

        system_prompt = """당신은 프로젝트 관리 보고서를 작성하는 전문가입니다.
주어진 데이터를 기반으로 발주처에게 보내는 정기 보고서를 작성해 주세요.

작성 원칙:
1. 구조화된 형식 (섹션별 구분)
2. 수치 데이터는 정확하게 반영
3. 진행 상황을 시각적으로 표현 (진행률 %)
4. 지연/이슈 사항은 원인과 대응 방안 함께 기술
5. 다음 기간 계획을 구체적으로
6. HTML 형식으로 출력 (이메일 발송 및 보고서 뷰 사용)
7. 간결하고 전문적인 어투

보고서 필수 섹션:
- 요약 (전체 진행률, 핵심 성과)
- 기간 내 완료 업무
- 진행 중 업무 현황
- 발주처 피드백 현황
- 이슈 및 지연 사항 (있는 경우)
- 다음 기간 계획

HTML 스타일 규칙:
- <h3>으로 섹션 구분
- <table>로 업무 목록 표시
- <div style="background:#4F46E5; ...">로 진행률 바 표현
- 색상: 완료=#10B981, 진행중=#3B82F6, 지연=#EF4444

반드시 아래 JSON 형식으로 응답하세요:
{"title": "보고서 제목", "content_html": "HTML 본문", "content_json": {"summary": "요약", "highlights": ["성과1"], "risks": ["리스크1"]}}"""

        # 완료 업무 텍스트
        completed = context.get("completed_tasks", [])
        completed_text = "\n".join(
            f"- {t.get('task_name', '')} ({t.get('phase', '')}, 완료: {t.get('completed_date', '')}, 담당: {t.get('assignee', '')})"
            for t in completed
        ) or "없음"

        # 진행 중 업무
        in_progress = context.get("in_progress_tasks", [])
        in_progress_text = "\n".join(
            f"- {t.get('task_name', '')} ({t.get('phase', '')}, 마감: {t.get('due_date', '')}, 담당: {t.get('assignee', '')})"
            for t in in_progress
        ) or "없음"

        # 예정 업무
        upcoming = context.get("upcoming_tasks", [])
        upcoming_text = "\n".join(
            f"- {t.get('task_name', '')} ({t.get('phase', '')}, 마감: {t.get('due_date', '')}, 담당: {t.get('assignee', '')})"
            for t in upcoming
        ) or "없음"

        # 피드백 요약
        fb = context.get("feedback_summary", {})
        fb_text = (
            f"확인: {fb.get('confirmed', 0)}건, "
            f"수정요청: {fb.get('revision_requested', 0)}건, "
            f"대기: {fb.get('pending', 0)}건"
        )

        # 이슈
        issues = context.get("issues", [])
        issues_text = "\n".join(f"- {i}" for i in issues) or "없음"

        # 전체 진행률
        op = context.get("overall_progress", {})
        progress_text = (
            f"{op.get('completed_tasks', 0)}/{op.get('total_tasks', 0)} "
            f"({op.get('progress_percent', 0)}%)"
        )

        user_prompt = (
            f"다음 데이터를 기반으로 정기 보고서를 작성해 주세요:\n\n"
            f"프로젝트: {context.get('project_name', '')}\n"
            f"발주처: {context.get('client_name', '')}\n"
            f"보고 기간: {context.get('period_start', '')} ~ {context.get('period_end', '')}\n"
            f"전체 진행률: {progress_text}\n\n"
            f"[기간 내 완료 업무]\n{completed_text}\n\n"
            f"[진행 중 업무]\n{in_progress_text}\n\n"
            f"[다음 기간 예정 업무]\n{upcoming_text}\n\n"
            f"[피드백 현황]\n{fb_text}\n\n"
            f"[이슈 사항]\n{issues_text}\n"
        )

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.2,
                        response_mime_type="application/json",
                        http_options=types.HttpOptions(timeout=60_000),
                    ),
                )
                result = self._parse_json_response(response.text)
                title = result.get("title", "")
                content_html = result.get("content_html", "")
                if not title or not content_html:
                    raise RuntimeError("AI가 유효한 보고서를 생성하지 못했습니다")
                return {
                    "title": title,
                    "content_html": content_html,
                    "content_json": result.get("content_json"),
                }
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                last_error = e
                logger.warning(f"정기 보고서 파싱 실패 (시도 {attempt + 1}/{MAX_RETRIES + 1}): {e}")
                if attempt < MAX_RETRIES:
                    continue
            except RuntimeError:
                raise
            except Exception as e:
                logger.error(f"정기 보고서 생성 실패: {e}")
                raise RuntimeError(f"AI 보고서 생성에 실패했습니다: {e}")

        raise RuntimeError(f"AI 보고서 생성에 실패했습니다: {last_error}")

    async def generate_completion_summary(self, context: dict) -> dict:
        """프로젝트 완료 보고서 생성 (title + content_html + content_json)"""

        system_prompt = """당신은 프로젝트 완료 보고서를 작성하는 전문가입니다.
프로젝트 전체 수행 결과를 종합하여 발주처에게 제출하는
최종 결과 보고서를 작성해 주세요.

작성 원칙:
1. 공식적이고 체계적인 보고서 형식
2. 데이터 기반의 객관적 서술
3. 단계별 수행 내역을 상세히 기록
4. 일정 준수율, 피드백 통계 등 수치 데이터 포함
5. HTML 형식으로 출력

필수 섹션:
1. 프로젝트 개요 (발주처, 기간)
2. 수행 범위 및 단계별 결과
3. 전체 업무 수행 현황 (완료 업무 테이블)
4. 일정 준수율 (계획 vs 실적)
5. 발주처 피드백 이력 요약
6. 특이사항 및 개선 제안

HTML 스타일 규칙:
- <h2>로 대제목, <h3>으로 소제목
- <table>로 데이터 표 작성 (border, padding 포함)
- 진행률/준수율은 색상 바로 시각화

반드시 아래 JSON 형식으로 응답하세요:
{"title": "보고서 제목", "content_html": "HTML 본문", "content_json": {"summary": "요약", "key_metrics": {"on_time_rate": 93}, "recommendations": ["제안1"]}}"""

        # 전체 업무 텍스트
        all_tasks = context.get("all_tasks", [])
        tasks_text = "\n".join(
            f"- {t.get('task_name', '')} | {t.get('phase', '')} | "
            f"{'정시' if t.get('is_on_time') else '지연'} | "
            f"완료: {t.get('completed_date', '')}"
            for t in all_tasks
        ) or "없음"

        phases = context.get("phases", [])
        fb = context.get("feedback_history", {})
        sched = context.get("schedule_adherence", {})

        user_prompt = (
            f"다음 데이터를 기반으로 프로젝트 완료 보고서를 작성해 주세요:\n\n"
            f"프로젝트: {context.get('project_name', '')}\n"
            f"발주처: {context.get('client_name', '')}\n"
            f"기간: {context.get('start_date', '')} ~ {context.get('end_date', '')}\n"
            f"단계: {' → '.join(phases)}\n\n"
            f"전체 업무 {len(all_tasks)}건\n"
            f"일정 준수율: {sched.get('on_time_rate', 0)}%\n"
            f"계획 기간: {sched.get('planned_days', 0)}일\n"
            f"실제 기간: {sched.get('actual_days', 0)}일\n\n"
            f"피드백: 총 {fb.get('total', 0)}건\n"
            f"  - 확인: {fb.get('confirmed', 0)}건\n"
            f"  - 수정 요청: {fb.get('revision_requested', 0)}건\n"
            f"  - 평균 응답: {fb.get('avg_response_days', 0)}일\n\n"
            f"[업무 상세]\n{tasks_text}\n"
        )

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.2,
                        response_mime_type="application/json",
                        http_options=types.HttpOptions(timeout=60_000),
                    ),
                )
                result = self._parse_json_response(response.text)
                title = result.get("title", "")
                content_html = result.get("content_html", "")
                if not title or not content_html:
                    raise RuntimeError("AI가 유효한 완료 보고서를 생성하지 못했습니다")
                return {
                    "title": title,
                    "content_html": content_html,
                    "content_json": result.get("content_json"),
                }
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                last_error = e
                logger.warning(f"완료 보고서 파싱 실패 (시도 {attempt + 1}/{MAX_RETRIES + 1}): {e}")
                if attempt < MAX_RETRIES:
                    continue
            except RuntimeError:
                raise
            except Exception as e:
                logger.error(f"완료 보고서 생성 실패: {e}")
                raise RuntimeError(f"AI 완료 보고서 생성에 실패했습니다: {e}")

        raise RuntimeError(f"AI 완료 보고서 생성에 실패했습니다: {last_error}")

    async def generate_estimate(self, context: dict) -> dict:
        """AI 견적서 생성 (items + total_amount + duration + notes)"""

        system_prompt = """당신은 IT 외주 견적 산정 전문가입니다.
프로젝트 범위와 과거 유사 프로젝트 데이터를 참고하여
견적서 초안을 작성해 주세요.

산정 원칙:
1. 과거 유사 프로젝트의 항목별 단가를 참고
2. 범위에 맞게 항목을 조정 (추가/제거/수량 변경)
3. 금액은 만원 단위로 반올림
4. 각 항목에 예상 소요일 포함
5. 총액과 총 소요일 계산
6. 참고한 과거 프로젝트 정보 명시

주의:
- 과거 데이터가 없으면 일반적인 IT 외주 시장 단가 기준으로 산정
- 금액은 VAT 별도
- 지나치게 낮거나 높은 금액 지양

반드시 아래 JSON 형식으로 응답하세요:
{
  "items": [
    {"name": "항목명", "description": "설명", "quantity": 1, "unit": "식", "unit_price": 3000000, "amount": 3000000, "estimated_days": 10}
  ],
  "total_amount": 42000000,
  "estimated_duration_days": 75,
  "notes": "산정 근거 설명",
  "reference_projects": ["참고 프로젝트명"]
}"""

        # 과거 프로젝트 텍스트
        past_projects = context.get("past_projects", [])
        if past_projects:
            past_text = "\n".join(
                f"- {p.get('project_name', '')} "
                f"(유형: {p.get('project_type', '')}, "
                f"금액: {p.get('contract_amount', '미정')}, "
                f"기간: {p.get('duration_days', '?')}일, "
                f"업무: {p.get('task_count', 0)}건)"
                + (
                    "\n  견적 항목: " + ", ".join(
                        f"{ei.get('name', '')}({ei.get('amount', 0):,}원/{ei.get('days', '?')}일)"
                        for ei in p.get("estimate_items", [])
                    )
                    if p.get("estimate_items") else ""
                )
                for p in past_projects
            )
        else:
            past_text = "참고 가능한 과거 프로젝트가 없습니다."

        user_prompt = (
            f"다음 프로젝트의 견적서를 작성해 주세요:\n\n"
            f"유형: {context.get('project_type', '')}\n"
            f"범위: {context.get('scope_description', '')}\n\n"
            f"[참고 과거 프로젝트]\n{past_text}\n"
        )

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.2,
                        response_mime_type="application/json",
                        http_options=types.HttpOptions(timeout=60_000),
                    ),
                )
                result = self._parse_json_response(response.text)
                items = result.get("items", [])
                total_amount = result.get("total_amount", 0)
                if not items or not total_amount:
                    raise RuntimeError("AI가 유효한 견적서를 생성하지 못했습니다")
                return {
                    "items": items,
                    "total_amount": total_amount,
                    "estimated_duration_days": result.get("estimated_duration_days", 0),
                    "notes": result.get("notes"),
                    "reference_projects": result.get("reference_projects", []),
                }
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                last_error = e
                logger.warning(f"견적서 파싱 실패 (시도 {attempt + 1}/{MAX_RETRIES + 1}): {e}")
                if attempt < MAX_RETRIES:
                    continue
            except RuntimeError:
                raise
            except Exception as e:
                logger.error(f"견적서 생성 실패: {e}")
                raise RuntimeError(f"AI 견적서 생성에 실패했습니다: {e}")

        raise RuntimeError(f"AI 견적서 생성에 실패했습니다: {last_error}")

    def _build_system_prompt(self) -> str:
        return """당신은 한국어 외주용역 계약서 분석 전문가입니다.
계약서 텍스트를 분석하여 추진 일정과 관련된 모든 정보를 체계적으로 추출해야 합니다.

다음 정보를 찾아 추출해 주세요:

1. **계약 기본 정보**
   - 계약명/사업명
   - 기업명 (계약 당사자 기업)
   - 수급자 (수급 업체)
   - 발주처 (발주 기관/업체)
   - 계약일 (계약 체결일)
   - 착수일 (사업 시작일)
   - 완수일 (사업 종료일)
   - 총 사업 기간
   - 계약 금액 (총 계약 금액, 원문 그대로)
   - 계약금 지급 방식 (일시불, 분할, 착수금/중도금/잔금 등)
   - 입금예정일 (대금 지급 예정일)

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
        "company_name": "기업명 또는 null",
        "contractor": "수급자 또는 null",
        "client": "발주처 또는 null",
        "contract_date": "YYYY-MM-DD 또는 원문 또는 null",
        "contract_start_date": "YYYY-MM-DD 또는 원문",
        "contract_end_date": "YYYY-MM-DD 또는 원문",
        "total_duration_days": 숫자 또는 null,
        "contract_amount": "계약 금액 원문 그대로 또는 null",
        "payment_method": "지급 방식 또는 null",
        "payment_due_date": "YYYY-MM-DD 또는 원문 또는 null",
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
