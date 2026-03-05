from fastapi import APIRouter
from app.api.endpoints import (
    upload, auth, contracts, teams, comments, notifications, activity, documents,
    clients, projects, tasks,  # Phase 0
    completion_reports, feedbacks,  # Phase 2
    reports,  # Phase 3
    payments, estimates,  # Phase 4
    templates,  # Phase 5
    portal, calendar,  # Phase 6
    dashboard,  # Phase 7
)

api_router = APIRouter()

# Phase 0 — 핵심 구조 (v2)
api_router.include_router(clients.router, prefix="/clients", tags=["발주처"])
api_router.include_router(projects.router, prefix="/projects", tags=["프로젝트"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["업무"])

# 기존 유지
api_router.include_router(upload.router, tags=["계약서 분석"])
api_router.include_router(auth.router, prefix="/auth", tags=["인증"])
api_router.include_router(contracts.router, prefix="/contracts", tags=["계약 관리"])
api_router.include_router(comments.router, prefix="/projects", tags=["댓글"])
api_router.include_router(teams.router, prefix="/teams", tags=["팀 관리"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["알림"])
api_router.include_router(activity.router, prefix="/activity", tags=["활동 로그"])
api_router.include_router(documents.router, tags=["문서 관리"])

# Phase 2 — 완료 보고 + 피드백
api_router.include_router(completion_reports.router, tags=["완료 보고"])
api_router.include_router(feedbacks.router, tags=["피드백"])

# Phase 3 — AI 보고서
api_router.include_router(reports.router, tags=["AI 보고서"])

# Phase 4 — 수금 관리 + AI 견적
api_router.include_router(payments.router, tags=["수금 관리"])
api_router.include_router(estimates.router, tags=["AI 견적"])

# Phase 5 — 템플릿 + 반복 업무
api_router.include_router(templates.router, tags=["템플릿 + 반복 업무"])

# Phase 6 — 클라이언트 포털 + 캘린더 연동
api_router.include_router(portal.router, tags=["클라이언트 포털"])
api_router.include_router(calendar.router, prefix="/calendar", tags=["캘린더 연동"])

# Phase 7 — 대시보드
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["대시보드"])
