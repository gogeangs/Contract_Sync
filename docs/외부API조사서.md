# 외부 API 조사서

> Contract Sync 프로젝트에서 사용할 외부 API 및 라이브러리 기술 조사 결과

---

## 목차
1. [Google Sheets API v4](#1-google-sheets-api-v4)
2. [Google Calendar API v3](#2-google-calendar-api-v3)
3. [Microsoft Graph API (Outlook)](#3-microsoft-graph-api-outlook)
4. [APScheduler](#4-apscheduler)
5. [aiosmtplib](#5-aiosmtplib)
6. [Google Gemini API](#6-google-gemini-api)
7. [Google OAuth2](#7-google-oauth2)
8. [Google Drive API v3](#8-google-drive-api-v3)

---

## 1. Google Sheets API v4

### 1-1. 개요
- **용도**: 견적서 CRUD, AI 파싱, 실시간 동기화
- **패키지**: `google-api-python-client`, `google-auth`
- **인증**: OAuth2 (사용자 대행) 또는 Service Account

### 1-2. 필요 OAuth Scope
```
https://www.googleapis.com/auth/spreadsheets        # 읽기/쓰기
https://www.googleapis.com/auth/spreadsheets.readonly  # 읽기 전용 (파싱만 할 때)
```

### 1-3. 핵심 메서드
| 메서드 | 설명 | 사용처 |
|--------|------|--------|
| `spreadsheets.create()` | 새 시트 생성 | 견적서 생성 |
| `spreadsheets.get()` | 시트 메타데이터 조회 | 시트 정보 확인 |
| `spreadsheets.values.get()` | 셀 데이터 읽기 | AI 파싱용 데이터 추출 |
| `spreadsheets.values.update()` | 셀 데이터 쓰기 | 견적서 편집 |
| `spreadsheets.values.batchUpdate()` | 여러 범위 일괄 쓰기 | 대량 업데이트 |
| `spreadsheets.values.append()` | 데이터 추가 | 행 추가 |
| `spreadsheets.batchUpdate()` | 서식/구조 변경 | 셀 병합, 색상 등 |

### 1-4. Rate Limit
- **읽기**: 분당 300 요청 / 프로젝트
- **쓰기**: 분당 60 요청 / 프로젝트
- **시트당**: 분당 60 요청
- 429 응답 시 지수 백오프(Exponential Backoff) 적용

### 1-5. FastAPI 비동기 통합 패턴
```python
import asyncio
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

async def read_sheet(credentials_dict: dict, spreadsheet_id: str, range_name: str):
    """Google Sheets API는 동기 라이브러리이므로 run_in_executor 사용"""
    creds = Credentials(**credentials_dict)
    service = build("sheets", "v4", credentials=creds)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
    )
    return result.get("values", [])
```

### 1-6. 프로젝트 적용 포인트
- `app/services/sheets_service.py`: 이미 생성됨, Sheets CRUD 로직 구현
- `app/api/endpoints/documents.py`: 시트 연결/생성/파싱 엔드포인트
- 시트 URL에서 ID 추출: `https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit`

---

## 2. Google Calendar API v3

### 2-1. 개요
- **용도**: 업무 일정 동기화, 마감일 자동 등록, 리마인더
- **패키지**: `google-api-python-client`
- **인증**: OAuth2 (사용자 대행)

### 2-2. 필요 OAuth Scope
```
https://www.googleapis.com/auth/calendar           # 읽기/쓰기
https://www.googleapis.com/auth/calendar.events     # 이벤트만
https://www.googleapis.com/auth/calendar.readonly   # 읽기 전용
```

### 2-3. 핵심 메서드
| 메서드 | 설명 | 사용처 |
|--------|------|--------|
| `events.insert()` | 이벤트 생성 | 업무 마감일 → 캘린더 등록 |
| `events.update()` | 이벤트 수정 | 마감일 변경 시 동기화 |
| `events.delete()` | 이벤트 삭제 | 업무 삭제 시 |
| `events.list()` | 이벤트 목록 조회 | 캘린더 뷰 데이터 |
| `events.watch()` | 변경 감지 Webhook | 양방향 동기화 |
| `calendarList.list()` | 사용자 캘린더 목록 | 캘린더 선택 UI |

### 2-4. 양방향 동기화 구조
```
[Contract Sync]  ──push──▶  [Google Calendar]
    업무 생성/수정             events.insert/update

[Google Calendar] ──webhook──▶ [Contract Sync]
    사용자가 직접 수정          events.watch → notification
                               → 변경 사항 반영
```

- **syncToken**: 증분 동기화용 토큰 (마지막 동기화 이후 변경분만 조회)
- **Webhook 수명**: 최대 7일 → 갱신 스케줄러 필요 (APScheduler)

### 2-5. Rate Limit
- 사용자당: 초당 10 쿼리
- 프로젝트당: 초당 100만 쿼리 (사실상 무제한)
- 캘린더당 이벤트 수: 최대 25,000개

### 2-6. FastAPI 비동기 통합
```python
async def create_calendar_event(credentials_dict: dict, event_data: dict):
    creds = Credentials(**credentials_dict)
    service = build("calendar", "v3", credentials=creds)

    loop = asyncio.get_event_loop()
    event = await loop.run_in_executor(
        None,
        lambda: service.events().insert(
            calendarId="primary",
            body=event_data
        ).execute()
    )
    return event

# 이벤트 데이터 구조
event_body = {
    "summary": "[Contract Sync] 디자인 시안 마감",
    "description": "프로젝트: ABC 웹사이트 / 업무: 디자인 시안",
    "start": {"dateTime": "2026-03-15T09:00:00+09:00", "timeZone": "Asia/Seoul"},
    "end": {"dateTime": "2026-03-15T18:00:00+09:00", "timeZone": "Asia/Seoul"},
    "reminders": {"useDefault": False, "overrides": [
        {"method": "popup", "minutes": 1440},  # D-1
        {"method": "popup", "minutes": 60},
    ]},
}
```

### 2-7. 프로젝트 적용 포인트
- `app/services/calendar_service.py`: 캘린더 CRUD + 동기화
- `app/api/endpoints/calendar.py`: 캘린더 연동/해제/동기화 엔드포인트
- DB `CalendarSync` 테이블: google_calendar_id, sync_token 저장

---

## 3. Microsoft Graph API (Outlook)

### 3-1. 개요
- **용도**: Outlook 캘린더 동기화 (Google Calendar 대안)
- **Base URL**: `https://graph.microsoft.com/v1.0`
- **인증**: Microsoft OAuth2 (Azure AD)
- **패키지**: `httpx` (REST API 직접 호출) 또는 `msgraph-sdk`

### 3-2. 필요 OAuth Scope
```
Calendars.ReadWrite      # 캘린더 읽기/쓰기
Mail.Send                # 이메일 발송 (선택)
User.Read                # 사용자 프로필
offline_access           # Refresh Token
```

### 3-3. 핵심 엔드포인트
| 엔드포인트 | 설명 |
|-----------|------|
| `POST /me/events` | 이벤트 생성 |
| `PATCH /me/events/{id}` | 이벤트 수정 |
| `DELETE /me/events/{id}` | 이벤트 삭제 |
| `GET /me/calendarView` | 기간별 이벤트 조회 |
| `POST /subscriptions` | Webhook 구독 (변경 감지) |
| `GET /me/events/delta` | 증분 동기화 (deltaLink) |

### 3-4. Google Calendar vs Outlook 비교
| 항목 | Google Calendar | Microsoft Graph |
|------|----------------|-----------------|
| 증분 동기화 | syncToken | deltaLink |
| Webhook | events.watch (7일) | subscriptions (3일) |
| SDK | google-api-python-client | msgraph-sdk / httpx |
| 인증 | Google OAuth2 | Azure AD OAuth2 |
| Rate Limit | 10 QPS/user | 10,000 req/10min/app |

### 3-5. 프로젝트 적용 방향
- **우선순위**: Google Calendar 먼저 구현, Outlook은 Phase 7 (확장)
- `app/services/calendar_service.py`에 Provider 패턴 적용:
  ```python
  class CalendarProvider(Protocol):
      async def create_event(self, event_data: dict) -> str: ...
      async def update_event(self, event_id: str, event_data: dict) -> None: ...
      async def delete_event(self, event_id: str) -> None: ...

  class GoogleCalendarProvider(CalendarProvider): ...
  class OutlookCalendarProvider(CalendarProvider): ...
  ```

---

## 4. APScheduler

### 4-1. 개요
- **용도**: 반복 업무 자동 생성, 리마인더, 수금 알림, AI 보고서 생성
- **패키지**: `apscheduler==3.10.4` (3.x 안정 버전 사용, 4.x는 알파)
- **스케줄러**: `AsyncIOScheduler` (FastAPI asyncio 호환)
- **JobStore**: `SQLAlchemyJobStore` (영속적 작업 저장)

### 4-2. FastAPI 통합 (Lifespan 패턴)
```python
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시
    scheduler.add_jobstore(
        SQLAlchemyJobStore(url=settings.database_url),
        alias="default"
    )
    scheduler.start()
    yield
    # 종료 시
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
```

### 4-3. Job 유형
| 트리거 | 설명 | 사용처 |
|--------|------|--------|
| `CronTrigger` | cron 표현식 | 매일/매주/매월 반복 업무 |
| `IntervalTrigger` | 고정 간격 | Webhook 갱신 (7일마다) |
| `DateTrigger` | 특정 일시 | 예약 이메일 발송 |

### 4-4. 프로젝트 사용 시나리오 (6가지)

**시나리오 1: 반복 업무 자동 생성**
```python
# 매주 월요일 09:00에 주간 업무 자동 생성
scheduler.add_job(
    create_recurring_tasks,
    CronTrigger(day_of_week="mon", hour=9, minute=0),
    id="recurring_weekly_tasks",
    replace_existing=True,
)
```

**시나리오 2: 고객 피드백 자동 확정 (7일)**
```python
# 완료보고 발송 7일 후 피드백 미응답 시 자동 확정
scheduler.add_job(
    auto_confirm_feedback,
    DateTrigger(run_date=report_sent_at + timedelta(days=7)),
    id=f"auto_confirm_{report_id}",
    args=[report_id],
)
```

**시나리오 3: 수금 D-Day 알림**
```python
# D-7, D-3, D-Day 수금 리마인더
for days_before in [7, 3, 0]:
    scheduler.add_job(
        send_payment_reminder,
        DateTrigger(run_date=due_date - timedelta(days=days_before)),
        id=f"payment_remind_{payment_id}_d{days_before}",
        args=[payment_id, days_before],
    )
```

**시나리오 4: 예약 이메일 발송**
```python
scheduler.add_job(
    send_scheduled_email,
    DateTrigger(run_date=scheduled_at),
    id=f"email_{report_id}",
    args=[report_id],
)
```

**시나리오 5: AI 정기 보고서 생성**
```python
# 매월 1일 주간/월간 AI 보고서 자동 생성
scheduler.add_job(
    generate_periodic_ai_report,
    CronTrigger(day=1, hour=2, minute=0),
    id="monthly_ai_report",
)
```

**시나리오 6: Google Calendar Webhook 갱신**
```python
# 6일마다 Webhook 갱신 (만료 전)
scheduler.add_job(
    renew_calendar_webhooks,
    IntervalTrigger(days=6),
    id="renew_webhooks",
)
```

### 4-5. 프로젝트 적용 포인트
- `app/services/scheduler_service.py`: 스케줄러 초기화 + 작업 등록/해제
- `main.py`: lifespan에 스케줄러 연동
- DB: SQLAlchemyJobStore가 `apscheduler_jobs` 테이블 자동 생성

---

## 5. aiosmtplib

### 5-1. 개요
- **용도**: 비동기 이메일 발송 (완료보고, 피드백 요청, 리마인더 등)
- **패키지**: `aiosmtplib` (이미 설치/사용 중)
- **현재 상태**: `app/services/email_service.py`에 인증코드 발송만 구현

### 5-2. 확장 기능 — HTML 이메일 + 첨부파일
```python
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from aiosmtplib import SMTP

async def send_email(
    to_emails: list[str],
    subject: str,
    html_body: str,
    cc_emails: list[str] | None = None,
    attachments: list[dict] | None = None,  # [{"filename": "...", "content": bytes}]
):
    message = MIMEMultipart("mixed")
    message["From"] = settings.smtp_from_email
    message["To"] = ", ".join(to_emails)
    message["Subject"] = subject
    if cc_emails:
        message["Cc"] = ", ".join(cc_emails)

    # HTML 본문
    message.attach(MIMEText(html_body, "html"))

    # 첨부파일
    if attachments:
        for att in attachments:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(att["content"])
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{att["filename"]}"')
            message.attach(part)

    # 수신자 목록 (To + Cc)
    recipients = list(to_emails)
    if cc_emails:
        recipients.extend(cc_emails)

    async with SMTP(
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        start_tls=settings.smtp_use_tls,
        username=settings.smtp_username,
        password=settings.smtp_password,
        timeout=30,
    ) as smtp:
        await smtp.send_message(message, recipients=recipients)
```

### 5-3. Jinja2 템플릿 통합
```python
from jinja2 import Environment, FileSystemLoader

# 템플릿 엔진 초기화
template_env = Environment(
    loader=FileSystemLoader("app/templates/email"),
    autoescape=True,
)

async def send_templated_email(
    template_name: str,
    context: dict,
    to_emails: list[str],
    subject: str,
    **kwargs,
):
    template = template_env.get_template(f"{template_name}.html")
    html_body = template.render(**context)
    await send_email(to_emails=to_emails, subject=subject, html_body=html_body, **kwargs)
```

### 5-4. 이메일 템플릿 목록 (기획서 기반)
| 템플릿 | 파일명 | 용도 |
|--------|--------|------|
| 완료보고서 | `completion_report.html` | 업무 완료 → 고객에게 발송 |
| 피드백 요청 | `feedback_request.html` | 완료보고 후 피드백 링크 |
| 피드백 확정 알림 | `feedback_confirmed.html` | 고객 피드백 확정 시 |
| 수정 요청 알림 | `revision_requested.html` | 고객 수정 요청 시 |
| 수금 리마인더 | `payment_reminder.html` | D-7, D-3, D-Day |
| AI 보고서 | `ai_report.html` | 정기/프로젝트 완료 보고서 |
| 인증코드 | `verification_code.html` | 회원가입/로그인 (기존) |

### 5-5. 에러 처리 & 재시도
```python
import asyncio
from aiosmtplib.errors import SMTPException

async def send_email_with_retry(max_retries: int = 3, **kwargs):
    for attempt in range(max_retries):
        try:
            await send_email(**kwargs)
            return True
        except SMTPException as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # 지수 백오프
                continue
            logger.error(f"이메일 발송 최종 실패: {e}")
            return False
```

### 5-6. 프로젝트 적용 포인트
- `app/services/email_service.py`: 기존 파일 확장 (범용 send_email + 템플릿 지원)
- `app/templates/email/`: 7개 Jinja2 HTML 템플릿 파일 생성
- 디자인: 인라인 CSS, max-width 600px, 브랜드 컬러 #4F46E5

---

## 6. Google Gemini API

### 6-1. 개요
- **용도**: 계약서 분석, 견적서 파싱, 핵심조항 추출, AI 보고서 생성
- **모델**: `gemini-2.0-flash` (빠르고 비용 효율적)
- **패키지**: `google-genai` (신규 통합 SDK)
- **현재 상태**: `app/services/gemini_service.py` 이미 존재

### 6-2. 비동기 호출 패턴
```python
from google import genai

client = genai.Client(api_key=settings.gemini_api_key)

async def analyze_contract(text: str) -> dict:
    """계약서 분석 — JSON 응답 모드"""
    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents=text,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,  # 분석은 낮은 temperature
            max_output_tokens=4096,
        ),
    )
    return json.loads(response.text)
```

### 6-3. 주요 사용 시나리오
| 시나리오 | 입력 | 출력 | Temperature |
|----------|------|------|-------------|
| 계약서 분석 | 계약서 텍스트 | 당사자, 기간, 금액, 핵심조항 | 0.1 |
| 견적서 파싱 | Sheets 데이터 | 항목별 금액, 합계, 예상기간 | 0.1 |
| 핵심 조항 추출 | 계약서 텍스트 | key_terms, risk_level | 0.1 |
| AI 보고서 생성 | 프로젝트 데이터 | HTML 보고서 | 0.3 |
| 업무 자동 추출 | 계약서 텍스트 | 업무 목록 + 예상 일정 | 0.2 |

### 6-4. 멀티모달 (PDF/이미지 분석)
```python
import pathlib

async def analyze_document_file(file_path: str) -> dict:
    """PDF/이미지 파일 직접 분석"""
    file = client.files.upload(file=pathlib.Path(file_path))

    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents=[file, "이 문서의 핵심 조항을 분석해주세요."],
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    return json.loads(response.text)
```

### 6-5. Rate Limit & 비용
- **무료 티어**: 분당 15 요청, 일 1,500 요청
- **유료 티어**: 분당 2,000 요청
- **입력**: $0.10 / 1M 토큰
- **출력**: $0.40 / 1M 토큰
- **컨텍스트 윈도우**: 1M 토큰 (긴 계약서도 가능)

### 6-6. 프롬프트 설계 원칙
1. **한국어 지시**: 프롬프트와 응답 모두 한국어
2. **JSON 스키마 명시**: 응답 구조를 프롬프트에 포함
3. **역할 부여**: "당신은 건설/IT 계약서 분석 전문가입니다"
4. **Few-shot 예시**: 복잡한 추출 시 예시 포함
5. **Hallucination 방지**: "문서에 없는 정보는 null로 표시"

### 6-7. 프로젝트 적용 포인트
- `app/services/gemini_service.py`: 기존 파일에 분석 함수 추가
- `app/services/ai_report_service.py`: AI 보고서 생성 전용 서비스
- 프롬프트 관리: `app/prompts/` 디렉토리 또는 DB 저장

---

## 7. Google OAuth2

### 7-1. 개요
- **용도**: 사용자 인증 + Google API 권한 위임
- **현재 상태**: Authlib로 Google 로그인 구현됨 (`openid email profile`)
- **확장 필요**: Sheets/Calendar/Drive 스코프 추가

### 7-2. OAuth2 Authorization Code Flow
```
[사용자] → [Contract Sync 프론트엔드]
    → /auth/google/login (state, code_verifier 생성)
    → Google 동의화면 (scope 요청)
    → /auth/google/callback (code 수신)
    → Google Token Endpoint (code → access_token + refresh_token)
    → DB에 토큰 저장
    → 세션 생성
```

### 7-3. Scope 확장 전략
```python
# 현재 (로그인만)
BASIC_SCOPES = ["openid", "email", "profile"]

# 확장 (Google 서비스 연동 시)
EXTENDED_SCOPES = [
    "openid", "email", "profile",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",
]
```

**Incremental Authorization (점진적 권한 요청)**:
- 로그인 시: 기본 스코프만 요청
- Sheets 연동 시: 추가 동의 화면 → Sheets 스코프 추가
- Calendar 연동 시: 추가 동의 화면 → Calendar 스코프 추가

### 7-4. Token 관리
```python
from google.oauth2.credentials import Credentials

def build_credentials(user_tokens: dict) -> Credentials:
    """DB 저장 토큰으로 Credentials 객체 생성"""
    return Credentials(
        token=user_tokens["access_token"],
        refresh_token=user_tokens["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=user_tokens.get("scopes", []),
    )

async def get_valid_credentials(user_id: int, db: AsyncSession) -> Credentials:
    """토큰 만료 시 자동 갱신"""
    tokens = await get_user_tokens(user_id, db)
    creds = build_credentials(tokens)

    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, creds.refresh, Request())
        # 갱신된 토큰 DB 업데이트
        await update_user_tokens(user_id, {
            "access_token": creds.token,
            "expiry": creds.expiry.isoformat(),
        }, db)

    return creds
```

### 7-5. 보안 요구사항
- **PKCE**: Authorization Code 가로채기 방지 (code_verifier + code_challenge)
- **state 파라미터**: CSRF 방지 (랜덤 문자열, 세션에 저장 후 검증)
- **Token 암호화**: DB에 저장 시 AES-256 암호화 권장
- **Refresh Token 보호**: 서버사이드에서만 사용, 클라이언트에 노출 금지
- **Scope 최소 권한**: 필요한 최소한의 scope만 요청

### 7-6. 프로젝트 적용 포인트
- `app/api/endpoints/auth.py`: 기존 Google 로그인에 scope 확장 로직 추가
- DB `User` 테이블: `google_tokens` (JSON, 암호화) 컬럼 활용
- `app/services/google_auth_service.py`: 토큰 관리 전용 서비스 (선택)

---

## 8. Google Drive API v3

### 8-1. 개요
- **용도**: 문서 파일 업로드/다운로드, 공유 설정, Sheets 파일 관리
- **패키지**: `google-api-python-client` (Sheets와 동일)
- **인증**: OAuth2 (사용자 대행)

### 8-2. 필요 OAuth Scope
```
https://www.googleapis.com/auth/drive.file    # 앱이 생성한 파일만 (최소 권한, 권장)
https://www.googleapis.com/auth/drive         # 전체 드라이브 (필요시에만)
```

### 8-3. 핵심 메서드
| 메서드 | 설명 | 사용처 |
|--------|------|--------|
| `files.create()` | 파일 업로드 | 문서 업로드/시트 생성 |
| `files.get()` | 파일 메타데이터 | 파일 정보 조회 |
| `files.list()` | 파일 검색 | 프로젝트 관련 파일 목록 |
| `files.update()` | 파일 업데이트 | 메타데이터 수정 |
| `files.delete()` | 파일 삭제 | 문서 삭제 |
| `files.export()` | 파일 내보내기 | Google Docs → PDF |
| `permissions.create()` | 공유 설정 | 고객에게 시트 공유 |
| `permissions.delete()` | 공유 해제 | 접근 권한 회수 |

### 8-4. 파일 업로드 패턴
```python
from googleapiclient.http import MediaIoBaseUpload
import io

async def upload_file_to_drive(
    credentials_dict: dict,
    file_content: bytes,
    file_name: str,
    mime_type: str,
    folder_id: str | None = None,
) -> dict:
    creds = Credentials(**credentials_dict)
    service = build("drive", "v3", credentials=creds)

    metadata = {"name": file_name}
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaIoBaseUpload(
        io.BytesIO(file_content),
        mimetype=mime_type,
        resumable=True,  # 대용량 파일 지원
    )

    loop = asyncio.get_event_loop()
    file = await loop.run_in_executor(
        None,
        lambda: service.files().create(
            body=metadata,
            media_body=media,
            fields="id, name, webViewLink, size"
        ).execute()
    )
    return file
```

### 8-5. Sheets 연동 — Drive + Sheets 통합
```python
# Google Sheets 파일 = Drive 파일 (application/vnd.google-apps.spreadsheet)
# Sheets API로 생성한 파일은 Drive에도 자동 존재

# Drive로 시트 검색
query = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"

# Drive로 시트 공유 설정
permission = {
    "type": "user",
    "role": "writer",  # reader, writer, commenter
    "emailAddress": "client@example.com",
}
service.permissions().create(
    fileId=sheet_id,
    body=permission,
    sendNotificationEmail=True,
).execute()
```

### 8-6. Rate Limit
- 사용자당: 초당 12 쿼리
- 프로젝트당: 초당 1,000 쿼리
- 업로드: 파일당 최대 5TB
- 429 응답 시 지수 백오프 적용

### 8-7. 프로젝트 적용 포인트
- `app/services/drive_service.py`: Drive 파일 CRUD + 공유 설정
- `app/services/sheets_service.py`와 연동 (시트 파일 = 드라이브 파일)
- 문서 저장 경로: 로컬 + Drive 이중 저장 (선택적)

---

## 공통 사항

### 설치 패키지 요약
```
# requirements.txt 추가 항목
google-api-python-client>=2.100.0   # Sheets, Calendar, Drive
google-auth>=2.23.0                 # OAuth2 credential 관리
google-genai>=1.0.0                 # Gemini API (신규 SDK)
apscheduler>=3.10.4,<4.0           # 스케줄러 (3.x 안정 버전)
aiosmtplib>=3.0.0                   # 이메일 (이미 설치)
jinja2>=3.1.0                       # 이메일 템플릿
httpx>=0.25.0                       # Outlook Graph API (Phase 7)
authlib>=1.3.0                      # OAuth2 (이미 설치)
```

### 환경변수 (config.py 추가)
```
# Google API
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# SMTP (기존)
SMTP_HOST=...
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...

# Gemini
GEMINI_API_KEY=...

# Microsoft (Phase 7)
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...
MICROSOFT_TENANT_ID=...
```

### 에러 처리 공통 패턴
```python
import asyncio
import logging

logger = logging.getLogger(__name__)

async def with_retry(func, *args, max_retries=3, **kwargs):
    """지수 백오프 재시도 래퍼"""
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"재시도 {attempt + 1}/{max_retries} ({wait}초 후): {e}")
                await asyncio.sleep(wait)
            else:
                logger.error(f"최종 실패: {e}")
                raise
```

### 서비스 파일 구조 (최종)
```
app/services/
├── __init__.py
├── email_service.py        ← 확장 (범용 발송 + 템플릿)
├── gemini_service.py       ← 확장 (분석 함수 추가)
├── sheets_service.py       ← 확장 (CRUD + AI 파싱)
├── file_service.py         ← 기존 유지
├── document_service.py     ← 기존 유지
├── drive_service.py        ← 신규 (Drive 파일 관리)
├── calendar_service.py     ← 신규 (캘린더 동기화)
├── scheduler_service.py    ← 신규 (APScheduler 관리)
├── ai_report_service.py    ← 신규 (AI 보고서 생성)
└── google_auth_service.py  ← 신규 (토큰 관리, 선택)
```
