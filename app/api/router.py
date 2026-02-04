from fastapi import APIRouter
from app.api.endpoints import upload, auth

api_router = APIRouter()

api_router.include_router(upload.router, tags=["계약서 분석"])
api_router.include_router(auth.router, prefix="/auth", tags=["인증"])
