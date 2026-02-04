from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path

from app.api.router import api_router
from app.config import settings
from app.database import init_db

# 앱 루트 디렉토리
BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(
    title="Contract Sync",
    description="외주용역 계약서에서 추진 일정을 추출하고 업무 목록을 생성하는 API",
    version="1.0.0",
)

# 세션 미들웨어 (Google OAuth에 필요)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 마운트
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# 템플릿 설정
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# API 라우터 등록
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    """앱 시작시 데이터베이스 초기화"""
    await init_db()


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """메인 페이지"""
    return templates.TemplateResponse("index.html", {"request": request})
