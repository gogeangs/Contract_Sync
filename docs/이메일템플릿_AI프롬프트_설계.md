# 이메일 템플릿 & AI 프롬프트 설계서

> 최종 업데이트: 2026-03-01
> 관련 문서: `기능명세서_v2.md` 9장(완료 보고), 10장(피드백), 11장(AI 보고서), 12장(AI 견적서)

---

## Part 1. 이메일 템플릿

### 공통 사항

- **렌더링 엔진:** Jinja2
- **파일 위치:** `app/templates/email/` (신규 디렉토리)
- **인코딩:** UTF-8
- **스타일:** inline CSS (이메일 클라이언트 호환)
- **반응형:** max-width 600px, 모바일 자동 축소
- **다크모드:** `@media (prefers-color-scheme: dark)` 미적용 (이메일 클라이언트 지원 불안정)
- **CAN-SPAM 준수:** 하단에 서비스명 + 수신거부 안내 문구 포함

### 공통 레이아웃 (base_email.html)

```
┌──────────────────────────────────────────────┐
│  [로고] Contract Sync                         │  ← 헤더 (브랜드 컬러 #4F46E5)
├──────────────────────────────────────────────┤
│                                              │
│  {메일 본문 콘텐츠}                            │  ← 컨텐츠 영역 (흰색 배경)
│                                              │
├──────────────────────────────────────────────┤
│  {사용자 서명 영역}                            │  ← 서명 (설정에서 커스터마이징)
├──────────────────────────────────────────────┤
│  Contract Sync | 본 메일은 발신 전용입니다.     │  ← 푸터 (회색)
│  문의: {발송자 이메일}                         │
└──────────────────────────────────────────────┘
```

**서명 커스터마이징:**
- 설정 페이지에서 회사명, 직함, 연락처, 로고 URL 설정 가능
- 미설정 시 기본 서명: 발송자 이름 + 이메일

---

### 템플릿 1. 인증코드 (기존)

**파일:** `verification_code.html`
**트리거:** 회원가입 시 이메일 인증
**수신자:** 가입 시도 사용자

| 변수 | 설명 | 예시 |
|------|------|------|
| `code` | 6자리 인증코드 | 482957 |

```
제목: [Contract Sync] 이메일 인증코드

본문:
─────────────────────────
Contract Sync 이메일 인증

아래 인증코드를 입력하여
이메일 인증을 완료하세요.

┌─────────────────────┐
│      4 8 2 9 5 7     │  ← 큰 글씨, 브랜드 컬러 배경
└─────────────────────┘

이 인증코드는 10분간 유효합니다.
─────────────────────────
```

> **변경 사항:** 기존 인라인 HTML을 Jinja2 템플릿 파일로 분리만 하면 됨. 내용 변경 없음.

---

### 템플릿 2. 완료 보고 (신규)

**파일:** `completion_report.html`
**트리거:** 업무 완료 후 "완료 보고 발송" 클릭
**수신자:** 발주처 담당자 (clients.contact_email)
**참조:** 사용자가 추가한 CC 이메일

| 변수 | 설명 | 예시 |
|------|------|------|
| `project_name` | 프로젝트명 | ABC 홈페이지 리뉴얼 |
| `task_name` | 업무명 | 메인 페이지 디자인 |
| `completed_date` | 완료일 | 2026-03-01 |
| `sender_name` | 담당자명 | 김개발 |
| `body_content` | AI 생성 + 사용자 편집 본문 | (아래 참조) |
| `attachments` | 첨부파일 목록 | [{name, size}] |
| `feedback_url` | 피드백 링크 | https://domain/feedback/abc123 |
| `sender_signature` | 서명 HTML | 회사명/직함/연락처 |

```
제목: [{{project_name}}] "{{task_name}}" 완료 안내

본문:
─────────────────────────────────────────
 프로젝트: {{project_name}}
 업무:     {{task_name}}
 완료일:   {{completed_date}}
 담당자:   {{sender_name}}
─────────────────────────────────────────

안녕하세요,

{{body_content}}

─── 첨부 파일 ───────────────────────────
 📎 메인페이지_시안_v3.psd (12.4MB)
 📎 디자인_가이드.pdf (2.1MB)
─────────────────────────────────────────

─── 피드백 요청 ─────────────────────────

아래 버튼을 눌러 업무 완료를 확인하거나
의견을 남겨주세요.

┌─────────────────────────────────────┐
│     [  피드백 남기기  ]              │  ← 브랜드 컬러 버튼
│     {{feedback_url}}                │
└─────────────────────────────────────┘

※ 7일 이내 응답이 없으면
  자동으로 "확인 완료" 처리됩니다.
─────────────────────────────────────────

{{sender_signature}}
```

**body_content 기본값 (AI가 생성하는 초안):**
```
{{task_name}} 업무가 완료되었습니다.

처리 내용:
{{note 내용 요약}}

첨부된 산출물을 확인해 주시기 바랍니다.
수정이 필요한 부분이 있으시면 피드백을 남겨주세요.
```

---

### 템플릿 3. 피드백 리마인더 (신규)

**파일:** `feedback_reminder.html`
**트리거:** 피드백 대기 상태에서 자동 확인 **3일 전** (Background task)
**수신자:** 발주처 담당자

| 변수 | 설명 |
|------|------|
| `project_name` | 프로젝트명 |
| `task_name` | 업무명 |
| `completed_date` | 완료일 |
| `sender_name` | 담당자명 |
| `auto_confirm_date` | 자동 확인 예정일 |
| `feedback_url` | 피드백 링크 |

```
제목: [리마인더] "{{task_name}}" 완료 확인 요청

본문:
─────────────────────────────────────────

안녕하세요,

{{project_name}} 프로젝트의
"{{task_name}}" 업무에 대한 완료 보고를
{{completed_date}}에 보내드렸습니다.

아직 피드백이 접수되지 않아
안내 드립니다.

┌─────────────────────────────────────┐
│  ⚠️  {{auto_confirm_date}}까지       │
│  응답이 없으면 자동으로              │
│  "확인 완료" 처리됩니다.             │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│     [  피드백 남기기  ]              │
└─────────────────────────────────────┘

─────────────────────────────────────────
```

---

### 템플릿 4. 자동 확인 알림 (신규)

**파일:** `auto_confirmed.html`
**트리거:** 7일 무응답으로 자동 확인 처리 시 (Background task)
**수신자:** 발주처 담당자 + 업무 담당자

| 변수 | 설명 |
|------|------|
| `project_name` | 프로젝트명 |
| `task_name` | 업무명 |
| `confirmed_date` | 자동 확인 처리일 |

```
제목: [자동 확인] "{{task_name}}" 업무가 확인 처리되었습니다

본문:
─────────────────────────────────────────

안녕하세요,

{{project_name}} 프로젝트의
"{{task_name}}" 업무 완료 보고에 대해
7일간 피드백이 접수되지 않아
{{confirmed_date}}에 자동으로 "확인 완료"
처리되었습니다.

추후 의견이 있으시면 담당자에게
직접 연락해 주시기 바랍니다.

─────────────────────────────────────────
```

---

### 템플릿 5. AI 정기 보고서 (신규)

**파일:** `periodic_report.html`
**트리거:** 정기 보고서를 사용자가 "발송" 클릭
**수신자:** 사용자가 지정한 이메일 (보통 발주처 담당자)

| 변수 | 설명 | 예시 |
|------|------|------|
| `project_name` | 프로젝트명 | ABC 홈페이지 |
| `report_type_label` | 보고 유형 라벨 | 주간 보고 |
| `period` | 대상 기간 | 2026.02.24 ~ 2026.02.28 |
| `report_html` | 보고서 본문 (HTML) | AI 생성 + 편집된 내용 |
| `sender_signature` | 서명 | 설정값 |

```
제목: [{{project_name}}] {{report_type_label}} ({{period}})

본문:
─────────────────────────────────────────
 프로젝트: {{project_name}}
 보고 유형: {{report_type_label}}
 대상 기간: {{period}}
─────────────────────────────────────────

{{report_html}}

─────────────────────────────────────────
본 보고서는 Contract Sync에서
자동 생성되었으며, 담당자가
검토·편집 후 발송하였습니다.
─────────────────────────────────────────

{{sender_signature}}
```

---

### 템플릿 6. 수금 마감 알림 (신규)

**파일:** `payment_reminder.html`
**트리거:** 결제 예정일 7일/3일/당일 전 (Background task, 내부 알림)
**수신자:** 프로젝트 담당자 (내부 사용자)

> 이 메일은 발주처가 아닌 **내부 담당자**에게 발송되는 리마인더이다.

| 변수 | 설명 | 예시 |
|------|------|------|
| `project_name` | 프로젝트명 | ABC 홈페이지 |
| `client_name` | 발주처명 | ABC 주식회사 |
| `payment_description` | 결제 설명 | 2차 중도금 |
| `amount` | 금액 | 10,000,000원 |
| `due_date` | 마감일 | 2026-03-15 |
| `days_left` | 남은 일수 | 7일 |
| `payment_url` | 수금 관리 링크 | /payments |

```
제목: [수금 알림] {{client_name}} - {{payment_description}} ({{days_left}} 남음)

본문:
─────────────────────────────────────────

 프로젝트:   {{project_name}}
 발주처:     {{client_name}}
 결제 항목:  {{payment_description}}
 금액:       {{amount}}
 예정일:     {{due_date}} ({{days_left}})

┌─────────────────────────────────────┐
│     [  수금 관리 바로가기  ]          │
└─────────────────────────────────────┘

─────────────────────────────────────────
```

**연체 시 (days_left가 음수):**
```
제목: [연체 알림] {{client_name}} - {{payment_description}} ({{overdue_days}}일 초과)

⚠️ 결제가 {{overdue_days}}일 연체되었습니다.
```

---

### 이메일 파일 구조

```
app/templates/email/
├── base_email.html              ← 공통 레이아웃 (헤더/푸터/서명)
├── verification_code.html       ← 인증코드 (기존 이전)
├── completion_report.html       ← 완료 보고
├── feedback_reminder.html       ← 피드백 리마인더
├── auto_confirmed.html          ← 자동 확인 알림
├── periodic_report.html         ← 정기 보고서
└── payment_reminder.html        ← 수금 알림
```

---

## Part 2. AI 프롬프트 설계

### 공통 사항

- **모델:** Gemini 2.0 Flash (`gemini-2.0-flash`)
- **temperature:** 0.1 (사실 기반 추출) ~ 0.3 (자연스러운 문장 생성)
- **응답 형식:** JSON (`response_mime_type: "application/json"`)
- **타임아웃:** 텍스트 120초 / 이미지 180초
- **재시도:** 파싱 실패 시 최대 2회
- **입력 텍스트 제한:** 12,000자 (초과 시 잘라서 전송)
- **보안:** AI 응답에 개인정보(이메일/전화번호) 포함 시 마스킹 처리

### 기존 프롬프트 (유지)

#### 프롬프트 0. 계약서 분석 (기존 유지)

> 현재 `gemini_service.py`의 `_build_system_prompt()` + `_build_json_format()`
> v2에서도 그대로 사용. 변경 없음.
> 단, 응답 내 `task_list`를 tasks 테이블에 INSERT하는 로직이 변경됨 (JSON → DB 레코드)

---

### 신규 프롬프트

#### 프롬프트 1. 완료 보고 초안 생성

**메서드:** `GeminiService.generate_completion_report_draft()`
**트리거:** 업무 완료 → "완료 보고 작성" 모달에서 자동 호출
**temperature:** 0.3

**입력 컨텍스트:**
```json
{
  "project_name": "프로젝트명",
  "client_name": "발주처명",
  "task_name": "업무명",
  "task_description": "업무 설명",
  "phase": "단계명",
  "note": "담당자가 작성한 처리 내용 메모",
  "attachments": ["파일명1.psd", "파일명2.pdf"],
  "completed_date": "2026-03-01"
}
```

**시스템 프롬프트:**
```
당신은 프로젝트 업무 완료 보고를 작성하는 비즈니스 커뮤니케이션 전문가입니다.
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
```

**사용자 프롬프트:**
```
다음 업무 완료 보고의 이메일 제목과 본문을 작성해 주세요:

프로젝트: {{project_name}}
업무명: {{task_name}}
단계: {{phase}}
완료일: {{completed_date}}
처리 내용: {{note}}
첨부 산출물: {{attachments | join(', ')}}
```

**응답 JSON:**
```json
{
  "subject": "[{{project_name}}] '{{task_name}}' 완료 안내",
  "body": "안녕하세요,\n\n{{project_name}} 프로젝트의 '{{task_name}}' 업무가 완료되어 안내 드립니다.\n\n처리 내용:\n{{요약 내용}}\n\n첨부된 산출물을 확인해 주시기 바랍니다.\n수정이 필요한 부분이 있으시면 피드백을 남겨주세요.\n\n감사합니다."
}
```

---

#### 프롬프트 2. 정기 보고서 생성 (일간/주간/월간)

**메서드:** `GeminiService.generate_periodic_report()`
**트리거:** Cron job에 의한 자동 생성 또는 사용자 수동 요청
**temperature:** 0.2

**입력 컨텍스트:**
```json
{
  "project_name": "프로젝트명",
  "client_name": "발주처명",
  "report_type": "weekly",
  "period_start": "2026-02-24",
  "period_end": "2026-02-28",
  "completed_tasks": [
    {
      "task_name": "메인 페이지 디자인",
      "phase": "디자인",
      "completed_date": "2026-02-25",
      "assignee": "김개발",
      "attachments": ["시안_v3.psd"],
      "feedback_status": "confirmed"
    }
  ],
  "in_progress_tasks": [
    {
      "task_name": "서브 페이지 개발",
      "phase": "개발",
      "status": "in_progress",
      "assignee": "이코딩",
      "due_date": "2026-03-07",
      "progress_note": "80% 진행"
    }
  ],
  "upcoming_tasks": [
    {
      "task_name": "QA 테스트",
      "phase": "테스트",
      "due_date": "2026-03-14",
      "assignee": "박테스트"
    }
  ],
  "feedback_summary": {
    "total": 5,
    "confirmed": 4,
    "revision_requested": 1,
    "pending": 0
  },
  "issues": [
    "서브 페이지 디자인 수정 요청으로 2일 지연"
  ],
  "overall_progress": {
    "total_tasks": 20,
    "completed_tasks": 12,
    "progress_percent": 60
  }
}
```

**시스템 프롬프트:**
```
당신은 프로젝트 관리 보고서를 작성하는 전문가입니다.
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
```

**사용자 프롬프트:**
```
다음 데이터를 기반으로 {{report_type_label}}를 작성해 주세요:

프로젝트: {{project_name}}
발주처: {{client_name}}
보고 기간: {{period_start}} ~ {{period_end}}
전체 진행률: {{overall_progress.completed_tasks}}/{{overall_progress.total_tasks}} ({{overall_progress.progress_percent}}%)

[기간 내 완료 업무]
{{completed_tasks를 줄바꿈으로 나열}}

[진행 중 업무]
{{in_progress_tasks를 줄바꿈으로 나열}}

[다음 기간 예정 업무]
{{upcoming_tasks를 줄바꿈으로 나열}}

[피드백 현황]
확인: {{feedback_summary.confirmed}}건
수정요청: {{feedback_summary.revision_requested}}건
대기: {{feedback_summary.pending}}건

[이슈 사항]
{{issues를 줄바꿈으로 나열, 없으면 "없음"}}
```

**응답 JSON:**
```json
{
  "title": "{{project_name}} 주간 보고 (2026.02.24~02.28)",
  "content_html": "<h3>1. 요약</h3><p>...</p><h3>2. 완료 업무</h3><table>...</table>...",
  "content_json": {
    "summary": "이번 주 3건의 업무를 완료하여 전체 진행률 60%를 달성했습니다.",
    "highlights": ["메인 페이지 디자인 확정", "API 개발 완료"],
    "risks": ["서브 페이지 디자인 수정으로 2일 지연"]
  }
}
```

---

#### 프롬프트 3. 프로젝트 완료 보고서 (결과 보고서)

**메서드:** `GeminiService.generate_completion_summary()`
**트리거:** 모든 업무 완료/확인 시 자동 생성 또는 수동 요청
**temperature:** 0.2

**입력 컨텍스트:**
```json
{
  "project_name": "프로젝트명",
  "client_name": "발주처명",
  "project_type": "outsourcing",
  "start_date": "2025-12-01",
  "end_date": "2026-02-28",
  "contract_amount": "50,000,000원",
  "all_tasks": [
    {
      "task_name": "요구사항 분석",
      "phase": "분석",
      "status": "confirmed",
      "assignee": "김개발",
      "start_date": "2025-12-01",
      "completed_date": "2025-12-14",
      "due_date": "2025-12-15",
      "is_on_time": true,
      "attachments": ["요구사항정의서.docx"]
    }
  ],
  "phases": ["분석", "설계", "개발", "테스트", "납품"],
  "feedback_history": {
    "total": 15,
    "confirmed": 14,
    "revision_requested": 1,
    "avg_response_days": 2.3
  },
  "payment_status": {
    "total_amount": 50000000,
    "paid_amount": 35000000,
    "remaining": 15000000
  },
  "schedule_adherence": {
    "planned_days": 90,
    "actual_days": 88,
    "on_time_rate": 93
  }
}
```

**시스템 프롬프트:**
```
당신은 프로젝트 완료 보고서를 작성하는 전문가입니다.
프로젝트 전체 수행 결과를 종합하여 발주처에게 제출하는
최종 결과 보고서를 작성해 주세요.

작성 원칙:
1. 공식적이고 체계적인 보고서 형식
2. 데이터 기반의 객관적 서술
3. 단계별 수행 내역을 상세히 기록
4. 일정 준수율, 피드백 통계 등 수치 데이터 포함
5. HTML 형식으로 출력

필수 섹션:
1. 프로젝트 개요 (발주처, 기간, 계약 금액)
2. 수행 범위 및 단계별 결과
3. 전체 업무 수행 현황 (완료 업무 테이블)
4. 산출물 목록 (제출일, 확인 상태)
5. 일정 준수율 (계획 vs 실적)
6. 발주처 피드백 이력 요약
7. 수금 현황
8. 특이사항 및 개선 제안

HTML 스타일 규칙:
- <h2>로 대제목, <h3>으로 소제목
- <table>로 데이터 표 작성 (border, padding 포함)
- 진행률/준수율은 색상 바로 시각화
```

**사용자 프롬프트:**
```
다음 데이터를 기반으로 프로젝트 완료 보고서를 작성해 주세요:

프로젝트: {{project_name}}
발주처: {{client_name}}
유형: {{project_type}}
기간: {{start_date}} ~ {{end_date}}
계약금액: {{contract_amount}}

단계: {{phases | join(' → ')}}

전체 업무 {{all_tasks | length}}건
일정 준수율: {{schedule_adherence.on_time_rate}}%
계획 기간: {{schedule_adherence.planned_days}}일
실제 기간: {{schedule_adherence.actual_days}}일

피드백: 총 {{feedback_history.total}}건
  - 확인: {{feedback_history.confirmed}}건
  - 수정 요청: {{feedback_history.revision_requested}}건
  - 평균 응답: {{feedback_history.avg_response_days}}일

수금: {{payment_status.paid_amount | format_currency}} / {{payment_status.total_amount | format_currency}}
잔액: {{payment_status.remaining | format_currency}}

[업무 상세]
{{all_tasks를 테이블 형태로 나열}}
```

**응답 JSON:**
```json
{
  "title": "{{project_name}} 프로젝트 완료 보고서",
  "content_html": "<h2>프로젝트 완료 보고서</h2>...",
  "content_json": {
    "summary": "3개월간 총 20건의 업무를 수행하여 프로젝트를 완료하였습니다.",
    "key_metrics": {
      "on_time_rate": 93,
      "feedback_satisfaction": 93.3,
      "payment_collection_rate": 70
    },
    "recommendations": [
      "향후 유사 프로젝트 시 디자인 검수 기간을 2일 추가 확보 권장"
    ]
  }
}
```

---

#### 프롬프트 4. AI 견적서 생성

**메서드:** `GeminiService.generate_estimate()`
**트리거:** "AI 견적서 생성" 버튼 클릭
**temperature:** 0.2

**입력 컨텍스트:**
```json
{
  "project_type": "outsourcing",
  "scope_description": "기업 홈페이지 리뉴얼 (반응형, 5페이지, 관리자 페이지 포함)",
  "past_projects": [
    {
      "project_name": "XYZ 홈페이지 제작",
      "project_type": "outsourcing",
      "contract_amount": "35,000,000원",
      "duration_days": 60,
      "task_count": 15,
      "phases": ["분석", "설계", "개발", "테스트"],
      "estimate_items": [
        {"name": "화면 설계", "amount": 5000000, "days": 14},
        {"name": "프론트엔드 개발", "amount": 12000000, "days": 21}
      ]
    }
  ]
}
```

**시스템 프롬프트:**
```
당신은 IT 외주 견적 산정 전문가입니다.
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
```

**사용자 프롬프트:**
```
다음 프로젝트의 견적서를 작성해 주세요:

유형: {{project_type}}
범위: {{scope_description}}

[참고 과거 프로젝트]
{{past_projects를 나열}}
```

**응답 JSON:**
```json
{
  "items": [
    {
      "name": "요구사항 분석",
      "description": "고객 요구사항 분석 및 정의서 작성",
      "quantity": 1,
      "unit": "식",
      "unit_price": 3000000,
      "amount": 3000000,
      "estimated_days": 10
    },
    {
      "name": "화면 설계 (5페이지 + 관리자)",
      "description": "반응형 UI/UX 설계, 프로토타입 제작",
      "quantity": 1,
      "unit": "식",
      "unit_price": 6000000,
      "amount": 6000000,
      "estimated_days": 14
    }
  ],
  "total_amount": 42000000,
  "estimated_duration_days": 75,
  "notes": "XYZ 홈페이지 제작 프로젝트(3,500만원/60일)를 기반으로 산정. 관리자 페이지 추가로 700만원/15일 증가 반영.",
  "reference_projects": ["XYZ 홈페이지 제작"]
}
```

---

#### 프롬프트 5. 핵심 조항 분석 (계약서 하이라이트)

**메서드:** `GeminiService.analyze_key_terms()`
**트리거:** document_type='contract'인 문서의 "핵심 조항 분석" 버튼 클릭
**temperature:** 0.1

**입력 컨텍스트:**
```json
{
  "document_title": "문서 제목",
  "raw_text": "계약서 전체 텍스트 (최대 12,000자)",
  "ai_analysis": "기존 AI 분석 결과 (있는 경우)"
}
```

**시스템 프롬프트:**
```
당신은 계약서 분석 전문 법률 보조 AI입니다.
외주용역 계약서에서 주요 조건과 위험 요소를 식별해 주세요.

분석 대상 조항:
1. 계약 금액 — 총액, 부가세 포함 여부, 지급 비율
2. 지급 조건 — 착수금/중도금/잔금 비율 및 시점
3. 지연 배상금 — 지연 시 배상 조건, 배상률 (%)
4. 하자 보수 — 하자 보증 기간, 무상 보수 범위
5. 지적재산권 — 저작권 귀속, 사용 권한, 소스코드 인도
6. 비밀유지 — 비밀유지 기간, 위반 시 제재
7. 계약 해지 — 해지 사유, 해지 시 정산 방법
8. 검수 기준 — 검수 절차, 기간, 불합격 시 처리

분석 원칙:
- 각 조항의 원문을 인용하고, 핵심 내용을 요약
- 수급자(용역 제공자) 관점에서 유불리를 판단
- 주의가 필요한 조항은 "⚠️ 주의" 표시
- 일반적인 관행과 다른 특이 조항 식별
```

**사용자 프롬프트:**
```
다음 계약서에서 핵심 조항을 분석해 주세요:

---
{{raw_text}}
---
```

**응답 JSON:**
```json
{
  "key_terms": [
    {
      "category": "계약 금액",
      "summary": "총 5,000만원 (VAT 별도), 착수금 30% / 중도금 40% / 잔금 30%",
      "original_text": "제5조 (계약금액) 계약금액은 금 50,000,000원(부가가치세 별도)으로 한다...",
      "risk_level": "normal",
      "note": null
    },
    {
      "category": "지연 배상금",
      "summary": "납기 지연 시 지연일수 × 계약금액의 0.1%, 최대 10%",
      "original_text": "제12조 (지체상금) 을이 납기를 지연한 때에는...",
      "risk_level": "warning",
      "note": "⚠️ 배상률 0.1%/일은 업계 평균(0.05~0.1%)의 상위 수준입니다."
    },
    {
      "category": "지적재산권",
      "summary": "납품 즉시 저작재산권 전부 이전, 소스코드 포함",
      "original_text": "제15조 (지적재산권) 본 계약에 의해 생성된 모든 산출물의...",
      "risk_level": "critical",
      "note": "⚠️ 소스코드 전체 이전 조건. 재사용 불가. 라이브러리/프레임워크 제외 조항 확인 필요."
    }
  ],
  "summary": "표준적인 외주용역 계약서이나, 지연 배상금과 지적재산권 조항에 주의가 필요합니다.",
  "overall_risk": "medium"
}
```

**risk_level 정의:**
| 값 | 의미 | UI 색상 |
|---|------|--------|
| `normal` | 일반적인 조건 | 초록 |
| `warning` | 주의 필요 | 노란색 |
| `critical` | 재검토 권장 | 빨간색 |

---

#### 프롬프트 6. 대시보드 AI 인사이트

**메서드:** `GeminiService.generate_insights()`
**트리거:** 대시보드 로드 시 (1시간 캐시)
**temperature:** 0.3

**입력 컨텍스트:**
```json
{
  "active_projects": 5,
  "overdue_tasks": [
    {"task_name": "API 개발", "project_name": "ABC 프로젝트", "overdue_days": 3}
  ],
  "overdue_payments": [
    {"client_name": "XYZ 회사", "amount": 10000000, "overdue_days": 15}
  ],
  "feedback_pending": [
    {"task_name": "디자인 시안", "project_name": "DEF 프로젝트", "waiting_days": 5}
  ],
  "upcoming_deadlines": [
    {"task_name": "QA 테스트", "project_name": "ABC 프로젝트", "due_date": "2026-03-05", "days_left": 4}
  ],
  "monthly_stats": {
    "completed_tasks": 12,
    "avg_completion_days": 5.2,
    "revenue": 15000000
  }
}
```

**시스템 프롬프트:**
```
당신은 프로젝트 관리 어시스턴트입니다.
현재 대시보드 데이터를 분석하여 사용자에게
실질적으로 도움이 되는 인사이트를 3~5개 제공해 주세요.

인사이트 유형:
- warning: 즉시 조치 필요 (마감 임박, 연체 등)
- info: 현황 요약 (진행 상황, 통계 등)
- suggestion: 개선 제안 (패턴 분석 기반)

원칙:
- 각 인사이트는 1문장, 최대 50자
- 데이터에 없는 내용 추측하지 않음
- 우선순위: warning > info > suggestion
```

**응답 JSON:**
```json
{
  "insights": [
    {
      "type": "warning",
      "message": "이번 주 마감 업무 5건 중 3건이 미완료입니다",
      "related_type": "task",
      "related_id": null
    },
    {
      "type": "warning",
      "message": "XYZ 회사 미수금이 15일 초과했습니다",
      "related_type": "payment",
      "related_id": null
    },
    {
      "type": "info",
      "message": "이번 달 업무 평균 처리 기간: 5.2일",
      "related_type": null,
      "related_id": null
    },
    {
      "type": "suggestion",
      "message": "DEF 프로젝트 피드백 5일 대기 중, 리마인더를 보내보세요",
      "related_type": "task",
      "related_id": null
    }
  ]
}
```

---

## Part 3. 구현 가이드 (백엔드 참조)

### 이메일 서비스 확장 방안

현재 `email_service.py`는 인증코드 발송만 지원한다.
v2에서는 다음과 같이 확장한다:

```python
# email_service.py 확장 구조 (의사코드)

class EmailService:
    def __init__(self):
        self.jinja_env = Environment(loader=FileSystemLoader("app/templates/email"))

    async def send_verification_code(self, to, code):
        """기존 유지"""

    async def send_completion_report(self, to, cc, subject, body, attachments, feedback_url, signature):
        """완료 보고 발송"""
        html = self._render("completion_report.html", {...})
        await self._send(to, cc, subject, html, attachments)

    async def send_feedback_reminder(self, to, project_name, task_name, ...):
        """피드백 리마인더"""

    async def send_auto_confirmed(self, to, project_name, task_name, ...):
        """자동 확인 알림"""

    async def send_periodic_report(self, to, subject, report_html, signature):
        """정기 보고서 발송"""

    async def send_payment_reminder(self, to, project_name, client_name, ...):
        """수금 알림"""

    def _render(self, template_name, context):
        """Jinja2 템플릿 렌더링"""

    async def _send(self, to, cc, subject, html, attachments=None):
        """공통 SMTP 발송 (첨부파일 지원)"""
```

### GeminiService 확장 방안

```python
# gemini_service.py 확장 구조 (의사코드)

class GeminiService:
    async def extract_schedule(self, ...):
        """기존 유지 — 계약서 분석"""

    async def generate_completion_report_draft(self, context: dict) -> dict:
        """프롬프트 1 — 완료 보고 초안"""

    async def generate_periodic_report(self, context: dict) -> dict:
        """프롬프트 2 — 정기 보고서"""

    async def generate_completion_summary(self, context: dict) -> dict:
        """프롬프트 3 — 프로젝트 완료 보고서"""

    async def generate_estimate(self, context: dict) -> dict:
        """프롬프트 4 — AI 견적서"""

    async def analyze_key_terms(self, raw_text: str) -> dict:
        """프롬프트 5 — 핵심 조항 분석"""

    async def generate_insights(self, context: dict) -> dict:
        """프롬프트 6 — 대시보드 인사이트"""
```

### 발송 제한

| 항목 | 제한 | 구현 |
|------|------|------|
| 사용자당 일일 발송 | 50회 | Redis 또는 DB 카운터 |
| 완료 보고 + 정기 보고 합산 | 50회/일 | 환경변수 EMAIL_DAILY_LIMIT |
| 피드백 페이지 Rate Limit | 10회/분/IP | SlowAPI |
