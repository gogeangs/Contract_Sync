from fastapi import APIRouter
from app.api.endpoints import upload, auth, contracts, teams, comments, notifications, activity

api_router = APIRouter()

api_router.include_router(upload.router, tags=["계약서 분석"])
api_router.include_router(auth.router, prefix="/auth", tags=["인증"])
api_router.include_router(contracts.router, prefix="/contracts", tags=["계약 관리"])
api_router.include_router(comments.router, prefix="/contracts", tags=["댓글"])
api_router.include_router(teams.router, prefix="/teams", tags=["팀 관리"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["알림"])
api_router.include_router(activity.router, prefix="/activity", tags=["활동 로그"])
