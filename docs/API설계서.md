# Contract Sync v2 — API 설계서

> 작성일: 2026-03-01
> 담당: 백엔드 개발자
> 기반 문서: `docs/기능명세서_v2.md`, `app/database.py` (v2 스키마)

---

## 목차

1. [공통 규칙](#1-공통-규칙)
2. [인증 (Auth)](#2-인증-auth) — 구현 완료
3. [발주처 (Clients)](#3-발주처-clients) — Phase 0
4. [프로젝트 (Projects)](#4-프로젝트-projects) — Phase 0
5. [업무 (Tasks)](#5-업무-tasks) — Phase 0
6. [문서 (Documents)](#6-문서-documents) — Phase 1 / 구현 완료
7. [Google Sheets 연동](#7-google-sheets-연동) — Phase 1 / 구현 완료
8. [문서 검토 (Reviews)](#8-문서-검토-reviews) — Phase 1 / 구현 완료
9. [완료 보고 (Completion Reports)](#9-완료-보고-completion-reports) — Phase 2
10. [클라이언트 피드백 (Feedbacks)](#10-클라이언트-피드백-feedbacks) — Phase 2
11. [AI 보고서 (AI Reports)](#11-ai-보고서-ai-reports) — Phase 3
12. [AI 견적서 생성](#12-ai-견적서-생성) — Phase 4
13. [수금 관리 (Payments)](#13-수금-관리-payments) — Phase 4
14. [프로젝트 템플릿](#14-프로젝트-템플릿) — Phase 5
15. [반복 업무](#15-반복-업무) — Phase 5
16. [클라이언트 포털](#16-클라이언트-포털) — Phase 6
17. [캘린더 연동](#17-캘린더-연동) — Phase 6
18. [대시보드](#18-대시보드) — Phase 7
19. [팀 관리 (Teams)](#19-팀-관리-teams) — 구현 완료
20. [댓글 (Comments)](#20-댓글-comments) — 기존 유지 + v2 확장
21. [알림 (Notifications)](#21-알림-notifications) — 구현 완료
22. [활동 로그 (Activity)](#22-활동-로그-activity) — 구현 완료
23. [에러 코드 체계](#23-에러-코드-체계)

---

## 1. 공통 규칙

### 1.1 Base URL

```
/api/v1
```

> 기존 v1 코드는 `/api` 프리픽스를 사용 중. v2 전환 시 `/api/v1` 으로 통일 예정.
> 전환 기간에는 기존 경로도 호환 유지.

### 1.2 인증

| 방식 | 적용 대상 |
|------|----------|
| **세션 쿠키** (`session_token`) | 모든 인증 필요 API |
| **토큰** (URL path) | 피드백 페이지, 클라이언트 포털 |
| **없음** | 인증 관련 API, 헬스체크 |

- HttpOnly, Secure(운영), SameSite=Lax
- 세션 유효 기간: 24시간

### 1.3 페이지네이션

```
GET /api/v1/{resource}?page=1&size=20
```

**응답 형식:**
```json
{
  "{resource}": [...],
  "total": 100
}
```

- `page`: 1부터 시작 (기본값: 1)
- `size`: 페이지 크기 (기본값: 20, 최대: 100)

### 1.4 에러 응답

```json
{
  "detail": "에러 메시지 (한국어)"
}
```

| HTTP 코드 | 의미 |
|-----------|------|
| 400 | 잘못된 요청 (유효성 검증 실패) |
| 401 | 인증 필요 |
| 403 | 권한 없음 |
| 404 | 리소스 없음 |
| 409 | 충돌 (중복 등) |
| 422 | Pydantic 유효성 오류 |
| 429 | Rate Limit 초과 |
| 500 | 서버 오류 |

### 1.5 Rate Limiting

| 카테고리 | 제한 |
|---------|------|
| 인증 (가입/로그인) | 3~5회/분 |
| CRUD (일반 조작) | 10~30회/분 |
| AI 분석/생성 | 3~5회/분 |
| 파일 업로드 | 10~20회/분 |
| 이메일 발송 | 사용자당 50회/일 |
| 피드백 (비로그인) | IP당 10회/분 |
| 포털 (비로그인) | 토큰당 60회/분 |

### 1.6 RBAC 권한 매트릭스

| 리소스 | owner | admin | member | viewer |
|--------|-------|-------|--------|--------|
| client.create/update | O | O | O | - |
| client.delete | O | O | - | - |
| project.create | O | O | O | - |
| project.update/delete | O | O | - | - |
| task.create/update/assign | O | O | O | - |
| task.delete | O | O | - | - |
| document.create/update | O | O | O | - |
| document.delete | O | O | - | - |
| report.create/send | O | O | O | - |
| payment.create/update | O | O | - | - |
| template.create/delete | O | O | - | - |
| comment.create | O | O | O | O |
| comment.delete_any | O | O | - | - |

---

## 2. 인증 (Auth)

> **상태: 구현 완료** (`app/api/endpoints/auth.py`)

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| POST | `/auth/send-code` | 인증코드 발송 (6자리, 10분 유효) | 5/분 |
| POST | `/auth/verify-code` | 인증코드 검증 | 5/분 |
| POST | `/auth/signup` | 회원가입 | 3/분 |
| POST | `/auth/login/email` | 이메일 로그인 | 3/분 |
| GET | `/auth/login/google` | Google OAuth 시작 | - |
| GET | `/auth/callback/google` | Google OAuth 콜백 | - |
| GET | `/auth/me` | 현재 사용자 조회 (팀 목록 포함) | - |
| PATCH | `/auth/profile` | 프로필 수정 (이름) | 10/분 |
| POST | `/auth/logout` | 로그아웃 | - |

### 요청/응답 예시

**POST /auth/signup**
```json
// Request
{ "email": "user@example.com", "password": "Pass1234!", "password_confirm": "Pass1234!" }

// Response 201
{ "user_id": 1, "session_token": "...", "team_id": 1 }
```

**GET /auth/me**
```json
// Response 200
{
  "user_id": 1,
  "email": "user@example.com",
  "name": "홍길동",
  "picture": null,
  "auth_provider": "email",
  "teams": [{ "team_id": 1, "name": "내 팀", "role": "owner" }]
}
```

---

## 3. 발주처 (Clients)

> **상태: Phase 0 — 미착수**
> 스키마: `app/schemas/client.py` ✅
> 서비스: `app/services/client_service.py` ❌
> 엔드포인트: `app/api/endpoints/clients.py` ❌

| 메서드 | 경로 | 설명 | Rate Limit | 권한 |
|--------|------|------|------------|------|
| POST | `/clients` | 발주처 등록 | 20/분 | client.create |
| GET | `/clients` | 발주처 목록 | - | 인증 |
| GET | `/clients/{id}` | 발주처 상세 (프로젝트/거래 포함) | - | 인증 |
| PUT | `/clients/{id}` | 발주처 수정 | 20/분 | client.update |
| DELETE | `/clients/{id}` | 발주처 삭제 | - | client.delete |
| GET | `/clients/{id}/projects` | 발주처의 프로젝트 목록 | - | 인증 |

### 요청 스키마 (ClientCreate)

```json
{
  "name": "주식회사 ABC",          // 필수, 1~200자
  "contact_name": "김담당",        // 선택, 100자
  "contact_email": "kim@abc.co",  // 선택, 이메일 형식 검증
  "contact_phone": "02-1234-5678",// 선택, 20자
  "address": "서울시 강남구...",    // 선택
  "category": "IT",              // 선택, 50자
  "memo": "메모"                  // 선택, 2000자
}
```

### 응답 스키마 (ClientResponse)

```json
{
  "id": 1,
  "user_id": 1,
  "team_id": 1,
  "name": "주식회사 ABC",
  "contact_name": "김담당",
  "contact_email": "kim@abc.co",
  "contact_phone": "02-1234-5678",
  "address": "서울시 강남구...",
  "category": "IT",
  "memo": "메모",
  "created_at": "2026-03-01T00:00:00",
  "updated_at": "2026-03-01T00:00:00",
  "active_project_count": 3,      // 집계
  "total_revenue": 50000000        // 집계 (paid 합산)
}
```

### 비즈니스 규칙

- 동일 팀 범위 내 발주처명 중복 불가
- 삭제 시 연관 프로젝트가 있으면 400 에러
- 목록 필터: `?search=`, `?category=`, `?page=`, `?size=`

---

## 4. 프로젝트 (Projects)

> **상태: Phase 0 — 미착수**
> 스키마: `app/schemas/project.py` ✅
> 서비스: `app/services/project_service.py` ❌
> 엔드포인트: `app/api/endpoints/projects.py` ❌
>
> 기존 `contracts.py` 코드를 v2 구조로 리팩토링해야 함.
> 전환 기간 중 `Contract = Project` 별칭으로 기존 프론트 호환 유지.

| 메서드 | 경로 | 설명 | Rate Limit | 권한 |
|--------|------|------|------------|------|
| POST | `/projects` | 프로젝트 생성 | 30/분 | project.create |
| GET | `/projects` | 프로젝트 목록 | - | 인증 |
| GET | `/projects/{id}` | 프로젝트 상세 (전체 탭 데이터) | - | 인증 |
| PUT | `/projects/{id}` | 프로젝트 수정 | 30/분 | project.update |
| DELETE | `/projects/{id}` | 프로젝트 삭제 | - | project.delete |
| PATCH | `/projects/{id}/status` | 상태 변경 | - | project.update |
| POST | `/projects/from-template/{template_id}` | 템플릿에서 생성 | 10/분 | project.create |

### 요청 스키마 (ProjectCreate)

```json
{
  "project_name": "웹사이트 개발",           // 필수, 1~500자
  "project_type": "outsourcing",            // outsourcing | internal | maintenance
  "client_id": 5,                           // 외주 필수, 내부 null
  "description": "프로젝트 설명",
  "start_date": "2026-03-01",
  "end_date": "2026-06-30",
  "total_duration_days": 120,
  "contract_amount": "50,000,000원",
  "payment_method": "착수금 30%, 중도금 40%, 잔금 30%",
  "schedules": [{"phase": "분석", "start": "03-01", "end": "03-15"}],
  "milestones": ["분석 완료", "개발 완료", "테스트 완료"]
}
```

### 응답 스키마 (ProjectResponse)

```json
{
  "id": 1,
  "user_id": 1,
  "team_id": 1,
  "client_id": 5,
  "project_name": "웹사이트 개발",
  "project_type": "outsourcing",
  "status": "active",
  "description": "...",
  "start_date": "2026-03-01",
  "end_date": "2026-06-30",
  "total_duration_days": 120,
  "contract_amount": "50,000,000원",
  "payment_method": "...",
  "schedules": [...],
  "milestones": [...],
  "report_opt_in": false,
  "report_frequency": null,
  "created_at": "2026-03-01T00:00:00",
  "updated_at": "2026-03-01T00:00:00",
  "client_name": "주식회사 ABC",     // 조인
  "task_count": 12,                 // 집계
  "completed_task_count": 5,        // 집계
  "document_count": 3               // 집계
}
```

### 상태 전이

```
planning → active ↔ on_hold → completed
                              → cancelled
```

- 모든 업무 완료/확인 시 → 자동 완료 제안 (프론트 confirm)
- `outsourcing` 유형은 `client_id` 필수

---

## 5. 업무 (Tasks)

> **상태: Phase 0 — 미착수**
> 스키마: `app/schemas/task.py` ✅
> 서비스: `app/services/task_service.py` ❌
> 엔드포인트: `app/api/endpoints/tasks.py` ❌
>
> 기존 `contracts.py`에 있는 task 관련 엔드포인트를 독립 tasks.py로 분리.
> v1 JSON 기반 → v2 독립 tasks 테이블.

| 메서드 | 경로 | 설명 | Rate Limit | 권한 |
|--------|------|------|------------|------|
| POST | `/tasks` | 업무 생성 | 30/분 | task.create |
| GET | `/tasks` | 업무 목록 (전체/프로젝트별) | - | 인증 |
| GET | `/tasks/{id}` | 업무 상세 (댓글/산출물/보고 포함) | - | 인증 |
| PUT | `/tasks/{id}` | 업무 수정 | 30/분 | task.update |
| DELETE | `/tasks/{id}` | 업무 삭제 | - | task.delete |
| PATCH | `/tasks/{id}/status` | 상태 변경 | - | task.update |
| PATCH | `/tasks/{id}/assignee` | 담당자 변경 | - | task.assign |
| PATCH | `/tasks/{id}/note` | 처리 내용 저장 (자동저장) | - | task.update |
| PATCH | `/tasks/{id}/move` | 프로젝트 이동 | 20/분 | task.update |
| POST | `/tasks/{id}/attachments` | 산출물 업로드 | 20/분 | task.update |
| DELETE | `/tasks/{id}/attachments/{att_id}` | 산출물 삭제 | - | task.update |
| GET | `/tasks/{id}/attachments/{att_id}` | 산출물 다운로드 | - | 인증 |
| PATCH | `/tasks/reorder` | 업무 순서 변경 (벌크) | 10/분 | task.update |

### 요청 스키마 (TaskCreate)

```json
{
  "task_name": "요구사항 분석",          // 필수, 1~300자
  "project_id": 1,                     // 선택 (null이면 프로젝트 미연결)
  "description": "상세 설명",
  "phase": "분석",                     // 200자
  "priority": "보통",                  // 긴급 | 높음 | 보통 | 낮음
  "due_date": "2026-03-15",
  "start_date": "2026-03-01",
  "assignee_id": 5,                   // 팀 멤버 ID
  "is_client_facing": true            // 발주처 대면 업무 여부
}
```

### 응답 스키마 (TaskResponse)

```json
{
  "id": 42,
  "task_code": "TASK-001",
  "project_id": 1,
  "user_id": 1,
  "team_id": 1,
  "task_name": "요구사항 분석",
  "description": "...",
  "phase": "분석",
  "status": "in_progress",
  "priority": "보통",
  "due_date": "2026-03-15",
  "start_date": "2026-03-01",
  "assignee_id": 5,
  "is_client_facing": true,
  "note": "처리 내용 메모",
  "sort_order": 0,
  "completed_at": null,
  "created_at": "2026-03-01T00:00:00",
  "updated_at": "2026-03-01T00:00:00",
  "assignee_name": "이개발",          // 조인
  "project_name": "웹사이트 개발",     // 조인
  "attachment_count": 3               // 집계
}
```

### 상태 전이 (일반 업무)

```
pending → in_progress → completed
```

### 상태 전이 (발주처 대면 업무: is_client_facing=true)

```
pending → in_progress → completed → report_sent → feedback_pending
                                                    ├→ confirmed
                                                    └→ revision_requested → in_progress (재작업)
```

- 7일 무응답 시 자동 confirmed 전환 (APScheduler)
- 3일 전 리마인더 이메일 발송

### 목록 필터

```
GET /tasks?project_id=1&status=pending&assignee_id=5&priority=높음&page=1&size=20
```

---

## 6. 문서 (Documents)

> **상태: Phase 1 — 구현 완료**
> 스키마: `app/schemas/document.py` ✅
> 서비스: `app/services/document_service.py` ✅
> 엔드포인트: `app/api/endpoints/documents.py` ✅

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| POST | `/projects/{project_id}/documents` | 문서 업로드 + AI 분석 | 10/분 |
| GET | `/projects/{project_id}/documents` | 프로젝트 문서 목록 | - |
| GET | `/documents/{id}` | 문서 상세 (분석 결과 포함) | - |
| PUT | `/documents/{id}` | 문서 정보 수정 | 20/분 |
| DELETE | `/documents/{id}` | 문서 삭제 | - |
| PATCH | `/documents/{id}/status` | 문서 상태 변경 | - |
| POST | `/documents/{id}/generate-tasks` | AI 분석 → 업무 일괄 생성 | 10/분 |
| GET | `/documents/{id}/versions` | 버전 이력 조회 | - |
| POST | `/documents/{id}/new-version` | 새 버전 업로드 | 10/분 |
| GET | `/documents/{id}/download` | 파일 다운로드 | - |

### 문서 유형

| 유형 | AI 분석 내용 |
|------|-------------|
| `estimate` | 항목명, 수량, 단가, 금액, 총액, 예상 기간 |
| `contract` | 계약 기본정보, 단계별 일정, 업무 목록 |
| `proposal` | 핵심 조건 (범위/일정/예산), 요약 |
| `other` | 텍스트 추출 (기본) |

### 지원 파일 형식

PDF, Word (.docx/.doc), 한글 (.hwp/.hwpx), 이미지 (.jpg/.png/.tiff/.bmp/.webp) — 최대 50MB

### 상태 전이

```
uploaded → analyzing → review_pending ↔ revision_requested → confirmed
```

---

## 7. Google Sheets 연동

> **상태: Phase 1 — 구현 완료**
> 서비스: `app/services/sheets_service.py` ✅

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| POST | `/projects/{project_id}/sheets/create` | 새 Google Sheet 생성 (견적서 템플릿) | 5/분 |
| POST | `/projects/{project_id}/sheets/link` | 기존 Sheet URL 연결 | 10/분 |
| GET | `/documents/{id}/sheet-data` | Sheet 내용 읽기 | - |
| POST | `/documents/{id}/sheet-parse` | AI로 Sheet 내용 파싱 | 5/분 |

### 기본 견적서 템플릿 헤더

```
No | 항목명 | 수량 | 단위 | 단가 | 금액 | 비고
```

### Sheet 파싱 결과

```json
{
  "estimate_items": [
    { "name": "화면 설계", "quantity": 1, "unit": "식", "unit_price": 5000000, "amount": 5000000, "estimated_days": 14 }
  ],
  "total_amount": 50000000,
  "estimated_duration_days": 120
}
```

---

## 8. 문서 검토 (Reviews)

> **상태: Phase 1 — 구현 완료**

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| POST | `/documents/{id}/reviews` | 검토자 지정 | 10/분 |
| GET | `/documents/{id}/reviews` | 검토 현황 조회 | - |
| PATCH | `/documents/{id}/reviews/{review_id}` | 검토 결과 제출 | - |
| POST | `/documents/{id}/ai-highlights` | AI 핵심 조항 분석 (계약서 전용) | 3/분 |

### 검토 프로세스

1. 문서 상태 `review_pending` 일 때 검토자 지정
2. 검토자에게 알림 발송
3. 검토자가 `approved` / `rejected` / `commented` 제출
4. 하나라도 `rejected` → 문서 상태 `revision_requested`
5. 모든 검토자 `approved` → 문서 상태 `confirmed` (자동)

### AI 핵심 조항 분석 대상

계약금액 / 지급조건 / 지연배상금 / 하자보수 / 지적재산권 / 비밀유지

---

## 9. 완료 보고 (Completion Reports)

> **상태: Phase 2 — 미착수**
> 스키마: `app/schemas/report.py` ✅ (CompletionReportCreate/Update/Response)
> DB 모델: `CompletionReport` ✅

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| POST | `/tasks/{id}/completion-report` | 완료 보고 작성 + 발송/예약 | 10/분 |
| GET | `/tasks/{id}/completion-report` | 완료 보고 조회 | - |
| PUT | `/completion-reports/{id}` | 완료 보고 수정 (예약 상태만) | 10/분 |
| DELETE | `/completion-reports/{id}` | 완료 보고 삭제 (예약 상태만) | - |
| POST | `/completion-reports/{id}/resend` | 재발송 | 5/분 |
| POST | `/tasks/{id}/ai-draft-report` | AI 보고 초안 생성 | 5/분 |

### 요청 스키마 (CompletionReportCreate)

```json
{
  "recipient_email": "client@example.com",
  "cc_emails": ["copy@example.com"],
  "subject": "[프로젝트명] \"업무명\" 완료 안내",
  "body_html": "<html>보고 내용</html>",
  "scheduled_at": "2026-03-25T14:00:00Z"  // null이면 즉시 발송
}
```

### 상태 전이

```
draft → scheduled → sent (또는 failed)
```

- 발송 실패 시 3회 재시도 (5분 간격)
- `feedback_token`: 64바이트 URL-safe 랜덤, 30일 유효
- 이메일 하단에 피드백 링크 자동 포함

---

## 10. 클라이언트 피드백 (Feedbacks)

> **상태: Phase 2 — 미착수**
> 스키마: `app/schemas/report.py` ✅ (FeedbackSubmit/Response)
> DB 모델: `ClientFeedback` ✅

| 메서드 | 경로 | 인증 | 설명 | Rate Limit |
|--------|------|------|------|------------|
| GET | `/feedback/{token}` | 토큰 | 피드백 페이지 (HTML 렌더링) | 60/분 |
| POST | `/api/v1/feedback/{token}` | 토큰 | 피드백 제출 | IP 10/분 |
| GET | `/tasks/{id}/feedbacks` | 세션 | 업무의 피드백 이력 | - |

### 요청 스키마 (FeedbackSubmit)

```json
{
  "feedback_type": "confirmed",    // confirmed | revision | comment
  "content": "수정 요청 내용...",    // 선택, 5000자
  "client_name": "김담당"           // 선택, 100자
}
```

### 피드백 유형별 동작

| 유형 | 업무 상태 변경 | 알림 |
|------|--------------|------|
| `confirmed` | → confirmed | 담당자에게 "확인 완료" 알림 |
| `revision` | → revision_requested | 담당자에게 "수정 요청" 알림 |
| `comment` | 변경 없음 | 담당자에게 "의견" 알림 |

### 자동 확인

- 7일 무응답 → 자동 confirmed 전환
- 3일 전 리마인더 이메일 발송 (발주처에게)
- `activity_log`에 `auto_confirm` 기록

---

## 11. AI 보고서 (AI Reports)

> **상태: Phase 3 — 미착수**
> 스키마: `app/schemas/report.py` ✅ (AIReportGenerate/Update/Send/Response)
> DB 모델: `AIReport` ✅

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| POST | `/projects/{id}/reports/generate` | AI 보고서 수동 생성 | 3/분 |
| GET | `/projects/{id}/reports` | 프로젝트 보고서 목록 | - |
| GET | `/reports` | 전체 보고서 목록 (보고서 허브) | - |
| GET | `/reports/{id}` | 보고서 상세 | - |
| PUT | `/reports/{id}` | 보고서 편집 (제목/본문) | 10/분 |
| POST | `/reports/{id}/send` | 보고서 이메일 발송 | 5/분 |
| DELETE | `/reports/{id}` | 보고서 삭제 | - |

### 보고서 유형

| 유형 | 트리거 | 내용 |
|------|--------|------|
| `periodic` | 수동 / 자동(주기 설정) | 기간 요약, 완료 업무, 피드백 현황, 이슈/지연 |
| `completion` | 모든 Task 완료 시 자동 제안 | 전체 수행 요약, 산출물 목록, 일정 준수율 |

### 정기 보고 설정 (프로젝트 단위)

```json
// PUT /projects/{id}
{
  "report_opt_in": true,
  "report_frequency": "weekly"    // daily | weekly | monthly
}
```

- 주간: 매주 금요일 (기본)
- 월간: 매월 마지막 영업일 (기본)
- 발송 방식: 검토 후 수동 발송 (기본)

---

## 12. AI 견적서 생성

> **상태: Phase 4 — 미착수**

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| POST | `/ai/estimate/generate` | AI 견적서 생성 | 3/분 |
| POST | `/ai/estimate/export-sheet` | Google Sheet로 내보내기 | 5/분 |

### 요청

```json
{
  "project_type": "outsourcing",
  "scope_description": "반응형 웹사이트 개발, 관리자 페이지 포함"
}
```

### 응답

```json
{
  "items": [
    { "name": "요구사항 분석", "quantity": 1, "unit": "식", "unit_price": 3000000, "amount": 3000000, "estimated_days": 10 }
  ],
  "total_amount": 50000000,
  "estimated_duration_days": 120,
  "notes": "과거 유사 프로젝트 3건 기반"
}
```

---

## 13. 수금 관리 (Payments)

> **상태: Phase 4 — 미착수**
> 스키마: `app/schemas/payment.py` ✅
> DB 모델: `PaymentSchedule` ✅

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| POST | `/projects/{id}/payments` | 결제 일정 등록 | 20/분 |
| GET | `/projects/{id}/payments` | 프로젝트 결제 일정 | - |
| PATCH | `/payments/{id}` | 결제 상태/금액 수정 | 20/분 |
| GET | `/payments/summary` | 전체 수금 요약 (대시보드) | - |
| GET | `/payments` | 수금 목록 (필터: status, page, size) | - |

### 결제 유형

| 유형 | 설명 |
|------|------|
| `advance` | 착수금 |
| `interim` | 중도금 |
| `final` | 잔금 |
| `milestone` | 마일스톤 기반 |

### 상태 전이

```
pending → invoiced → paid
pending → overdue → paid
```

### 알림 규칙

| 시점 | 알림 |
|------|------|
| D-7 | "결제 예정일이 7일 남았습니다" |
| D-3 | "결제 예정일이 3일 남았습니다" |
| D-Day | "오늘이 결제 예정일입니다" |
| D+1~ | "결제가 연체되었습니다" (매일, 상태 → overdue) |

---

## 14. 프로젝트 템플릿

> **상태: Phase 5 — 미착수**
> 스키마: `app/schemas/template.py` ✅
> DB 모델: `ProjectTemplate` ✅

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| POST | `/templates` | 템플릿 저장 | 10/분 |
| GET | `/templates` | 템플릿 목록 | - |
| GET | `/templates/{id}` | 템플릿 상세 | - |
| PUT | `/templates/{id}` | 템플릿 수정 | 10/분 |
| DELETE | `/templates/{id}` | 템플릿 삭제 | - |

### 템플릿 구조

```json
{
  "name": "웹개발 프로젝트",
  "project_type": "outsourcing",
  "task_templates": [
    {
      "task_name": "요구사항 분석",
      "phase": "분석",
      "relative_due_days": 14,
      "priority": "높음",
      "is_client_facing": true
    }
  ],
  "schedule_templates": [
    { "phase": "분석", "relative_start_days": 0, "duration_days": 14 }
  ]
}
```

- 프로젝트 생성 시 `POST /projects/from-template/{template_id}` 사용
- `relative_due_days`: 프로젝트 시작일 기준 상대 일수

---

## 15. 반복 업무

> **상태: Phase 5 — 미착수**
> 스키마: `app/schemas/template.py` ✅ (RecurringTaskCreate/Update/Response)
> DB 모델: `RecurringTask` ✅

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| POST | `/projects/{id}/recurring-tasks` | 반복 업무 설정 | 10/분 |
| GET | `/projects/{id}/recurring-tasks` | 반복 업무 목록 | - |
| PATCH | `/recurring-tasks/{id}` | 반복 업무 수정/비활성화 | 10/분 |

### 주기 설정

| 주기 | 파라미터 |
|------|---------|
| `daily` | 매일 (영업일만) |
| `weekly` | `day_of_week` (0=월 ~ 6=일) |
| `monthly` | `day_of_month` (1~31) |

- 백그라운드: APScheduler로 매일 00:00 KST에 자동 생성
- `last_generated_at`으로 중복 방지

---

## 16. 클라이언트 포털

> **상태: Phase 6 — 미착수**
> 스키마: `app/schemas/portal.py` ✅
> DB 모델: `PortalToken` ✅

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| GET | `/portal/{token}` | 토큰 | 포털 페이지 (HTML) |
| GET | `/api/v1/portal/{token}/data` | 토큰 | 포털 데이터 (JSON) |
| POST | `/projects/{id}/portal-token` | 세션 | 포털 토큰 발급 |
| DELETE | `/portal-tokens/{id}` | 세션 | 포털 토큰 폐기 |

### 포털 표시 항목

- 프로젝트명, 기간, 전체 진행률
- 업무 목록 (업무명, 상태, 마감일만)
- 산출물 다운로드 (완료 보고 첨부)
- 피드백 대기 항목 (직접 피드백 가능)
- 보고서 열람 (발송된 보고서)

### 토큰 규칙

- URL-safe 64바이트 랜덤
- 유효기간: 프로젝트 종료일 + 30일
- 발주처별/프로젝트별 1개 토큰

---

## 17. 캘린더 연동

> **상태: Phase 6 — 미착수**
> 스키마: `app/schemas/portal.py` ✅ (CalendarConnectRequest/StatusResponse)
> DB 모델: `CalendarSync`, `CalendarEvent` ✅

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| POST | `/calendar/connect/google` | Google Calendar 연결 | 3/분 |
| POST | `/calendar/connect/outlook` | Outlook 연결 | 3/분 |
| DELETE | `/calendar/disconnect` | 연동 해제 | - |
| POST | `/calendar/sync` | 수동 동기화 트리거 | 5/분 |
| GET | `/calendar/status` | 연동 상태 조회 | - |

### 동기화 규칙

- 대상: `due_date`가 있는 업무
- 이벤트 제목: `[CS] {업무명}`
- 양방향: 캘린더 변경 → 업무 마감일 갱신
- OAuth 토큰: AES-256 암호화 저장
- 자동 동기화: 30분 간격 (APScheduler)

---

## 18. 대시보드

> **상태: Phase 7 — 미착수**
> 스키마: `app/schemas/dashboard.py` ✅

| 메서드 | 경로 | 설명 | Rate Limit |
|--------|------|------|------------|
| GET | `/dashboard/summary` | 대시보드 통계 (6개 카드) | - |
| GET | `/dashboard/revenue` | 매출 추이 | - |
| GET | `/dashboard/workload` | 팀 워크로드 | - |
| GET | `/dashboard/ai-insights` | AI 인사이트 (1시간 캐시) | 3/분 |

### 통계 카드

```json
{
  "active_projects": 5,
  "pending_tasks": 12,
  "in_progress_tasks": 8,
  "monthly_revenue": 15000000,
  "outstanding_amount": 5000000,
  "feedback_pending_tasks": 3
}
```

### AI 인사이트 예시

```json
[
  { "type": "warning", "message": "이번 주 마감 업무 5건 중 3건이 미완료입니다", "related_type": "task" },
  { "type": "warning", "message": "A 발주처의 미수금이 30일 초과했습니다", "related_id": 5, "related_type": "payment" },
  { "type": "suggestion", "message": "웹개발 프로젝트 평균 견적 대비 실제 공수 120% 초과 추세" }
]
```

---

## 19. 팀 관리 (Teams)

> **상태: 구현 완료** (`app/api/endpoints/teams.py`)

| 메서드 | 경로 | 설명 | 권한 |
|--------|------|------|------|
| POST | `/teams` | 팀 생성 | 인증 |
| GET | `/teams` | 내 팀 목록 | 인증 |
| GET | `/teams/{id}` | 팀 상세 (멤버 포함) | 인증 |
| PUT | `/teams/{id}` | 팀 수정 | owner/admin |
| DELETE | `/teams/{id}` | 팀 삭제 | owner |
| POST | `/teams/{id}/members` | 멤버 초대 (이메일) | owner/admin |
| DELETE | `/teams/{id}/members/{user_id}` | 멤버 제거 | owner/admin (자기 자신도 가능) |
| PATCH | `/teams/{id}/members/{user_id}/role` | 역할 변경 | owner |
| GET | `/teams/{id}/permissions` | 내 권한 조회 | 인증 |

---

## 20. 댓글 (Comments)

> **상태: 구현 완료** (`app/api/endpoints/comments.py`)
> v2 변경: `contract_id` → `project_id`, `task_id`/`document_id` FK 추가

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/contracts/{project_id}/comments` | 댓글 목록 (task_id, document_id 필터) |
| POST | `/contracts/{project_id}/comments` | 댓글 작성 |
| PUT | `/contracts/{project_id}/comments/{id}` | 댓글 수정 (본인만) |
| DELETE | `/contracts/{project_id}/comments/{id}` | 댓글 삭제 (본인 또는 owner/admin) |

> **v2 리팩토링 필요**: 경로를 `/projects/{project_id}/comments`로 변경

---

## 21. 알림 (Notifications)

> **상태: 구현 완료** (`app/api/endpoints/notifications.py`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/notifications` | 알림 목록 (unread_only, page, size) |
| GET | `/notifications/unread-count` | 미읽음 수 |
| PATCH | `/notifications/{id}/read` | 읽음 처리 |
| PATCH | `/notifications/read-all` | 전체 읽음 |
| DELETE | `/notifications/{id}` | 알림 삭제 |

### v2 신규 알림 유형

| 유형 | 트리거 |
|------|--------|
| `feedback_received` | 발주처가 피드백 제출 |
| `revision_requested` | 발주처가 수정 요청 |
| `report_ready` | AI 보고서 생성 완료 |
| `payment_due` | 결제 예정일 D-7/3/0 |
| `payment_overdue` | 결제 연체 |
| `auto_confirmed` | 7일 무응답 자동 확인 |
| `recurring_task` | 반복 업무 자동 생성 |
| `calendar_sync_error` | 캘린더 동기화 오류 |

---

## 22. 활동 로그 (Activity)

> **상태: 구현 완료** (`app/api/endpoints/activity.py`)
> v2 변경: `contract_id` → `project_id`, `client_id` 추가

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/activity` | 활동 로그 (project_id, team_id, page, size) |

### v2 추가 추적 대상

| action | target_type | 설명 |
|--------|-------------|------|
| create/update/delete | client | 발주처 생성/수정/삭제 |
| confirm | document | 문서 확정 |
| send | completion_report | 완료 보고 발송 |
| receive | feedback | 피드백 수신 |
| generate/send | ai_report | AI 보고서 생성/발송 |
| update | payment | 결제 상태 변경 |
| auto_confirm | task | 자동 확인 전환 |

---

## 23. 에러 코드 체계

### 공통 에러

| 코드 | detail | 설명 |
|------|--------|------|
| 400 | "유효하지 않은 {필드}입니다" | 비즈니스 유효성 실패 |
| 401 | "로그인이 필요합니다" | 세션 없음/만료 |
| 403 | "접근 권한이 없습니다" | RBAC 권한 부족 |
| 404 | "{리소스}를 찾을 수 없습니다" | 리소스 없음 |
| 409 | "이미 존재하는 {리소스}입니다" | 중복 충돌 |
| 422 | Pydantic 자동 생성 | 스키마 유효성 오류 |
| 429 | "요청이 너무 많습니다" | Rate Limit 초과 |
| 500 | "{작업}에 실패했습니다: {원인}" | 서버 내부 오류 |

### 도메인 특화 에러

| 도메인 | 상황 | 코드 | detail |
|--------|------|------|--------|
| 발주처 | 연관 프로젝트 존재 시 삭제 | 400 | "연관 프로젝트가 있어 삭제할 수 없습니다" |
| 프로젝트 | 외주인데 client_id 없음 | 400 | "외주 프로젝트는 발주처 지정이 필수입니다" |
| 프로젝트 | 유효하지 않은 상태 전이 | 400 | "'{현재}' → '{대상}' 상태 변경이 불가합니다" |
| 업무 | 담당자가 팀 멤버 아님 | 400 | "팀 멤버만 담당자로 지정할 수 있습니다" |
| 문서 | 지원하지 않는 파일 형식 | 400 | "지원하지 않는 파일 형식입니다" |
| 문서 | 파일 크기 초과 | 400 | "파일 크기는 50MB를 초과할 수 없습니다" |
| 검토 | 이미 처리된 검토 | 400 | "이미 처리된 검토입니다" |
| 완료보고 | 예약 상태 아닌데 수정 시도 | 400 | "예약 상태의 보고만 수정할 수 있습니다" |
| 피드백 | 토큰 만료 | 403 | "피드백 링크가 만료되었습니다" |
| 수금 | 유효하지 않은 결제 상태 전이 | 400 | "유효하지 않은 결제 상태 변경입니다" |
| 포털 | 토큰 만료/비활성 | 403 | "포털 접근 권한이 만료되었습니다" |

---

## 부록: 구현 현황 요약

### 파일별 구현 상태

| 구분 | 파일 | 상태 |
|------|------|------|
| **Schemas** | `schedule.py` | ✅ v1 유지 |
| | `document.py` | ✅ v2 완료 |
| | `client.py` | ✅ v2 완료 |
| | `project.py` | ✅ v2 완료 |
| | `task.py` | ✅ v2 완료 |
| | `report.py` | ✅ v2 완료 |
| | `payment.py` | ✅ v2 완료 |
| | `template.py` | ✅ v2 완료 |
| | `portal.py` | ✅ v2 완료 |
| | `dashboard.py` | ✅ v2 완료 |
| **Services** | `document_service.py` | ✅ v2 완료 |
| | `sheets_service.py` | ✅ v2 완료 |
| | `gemini_service.py` | ✅ v1 유지 (재사용) |
| | `file_service.py` | ✅ v1 유지 (재사용) |
| | `email_service.py` | ✅ v1 유지 (재사용) |
| | `client_service.py` | ❌ Phase 0 |
| | `project_service.py` | ❌ Phase 0 |
| | `task_service.py` | ❌ Phase 0 |
| | `completion_service.py` | ❌ Phase 2 |
| | `feedback_service.py` | ❌ Phase 2 |
| | `report_service.py` | ❌ Phase 3 |
| | `payment_service.py` | ❌ Phase 4 |
| | `template_service.py` | ❌ Phase 5 |
| | `portal_service.py` | ❌ Phase 6 |
| | `calendar_service.py` | ❌ Phase 6 |
| | `dashboard_service.py` | ❌ Phase 7 |
| **Endpoints** | `auth.py` | ✅ v1 유지 |
| | `upload.py` | ✅ v1 유지 (재사용) |
| | `contracts.py` | ⚠️ v1 유지 → v2 리팩토링 필요 |
| | `teams.py` | ✅ v1 유지 |
| | `comments.py` | ⚠️ v1 유지 → v2 경로 변경 필요 |
| | `notifications.py` | ✅ v1 유지 |
| | `activity.py` | ⚠️ v1 유지 → v2 경로 변경 필요 |
| | `documents.py` | ✅ v2 완료 |
| | `clients.py` | ❌ Phase 0 |
| | `projects.py` | ❌ Phase 0 |
| | `tasks.py` | ❌ Phase 0 |
| | `completion_reports.py` | ❌ Phase 2 |
| | `feedbacks.py` | ❌ Phase 2 |
| | `reports.py` | ❌ Phase 3 |
| | `payments.py` | ❌ Phase 4 |
| | `templates.py` | ❌ Phase 5 |
| | `portal.py` | ❌ Phase 6 |
| | `calendar.py` | ❌ Phase 6 |
| | `dashboard.py` | ❌ Phase 7 |

### Phase별 엔드포인트 수

| Phase | 범위 | 엔드포인트 수 | 상태 |
|-------|------|-------------|------|
| 기존 | Auth, Teams, Upload, Notifications, Activity | 26 | ✅ 완료 |
| 기존 (v1) | Contracts (JSON tasks), Comments | 21 | ⚠️ 리팩토링 필요 |
| Phase 1 | Documents, Sheets, Reviews | 18 | ✅ 완료 |
| Phase 0 | Clients, Projects, Tasks | 26 | ❌ 미착수 |
| Phase 2 | Completion Reports, Feedbacks | 9 | ❌ 미착수 |
| Phase 3 | AI Reports | 7 | ❌ 미착수 |
| Phase 4 | Payments, AI 견적서 | 7 | ❌ 미착수 |
| Phase 5 | Templates, Recurring Tasks | 8 | ❌ 미착수 |
| Phase 6 | Portal, Calendar | 9 | ❌ 미착수 |
| Phase 7 | Dashboard | 4 | ❌ 미착수 |
| **합계** | | **~135** | |
