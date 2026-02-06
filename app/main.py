from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path
import logging
import sys

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

logger.info("Starting Contract Sync application...")

from app.api.router import api_router
from app.config import settings
from app.database import init_db

# 앱 루트 디렉토리
BASE_DIR = Path(__file__).resolve().parent.parent

# uploads 디렉토리 생성
uploads_dir = BASE_DIR / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
logger.info(f"Uploads directory: {uploads_dir}")

app = FastAPI(
    title="Contract Sync",
    description="외주용역 계약서에서 추진 일정을 추출하고 업무 목록을 생성하는 API",
    version="1.0.0",
)

# 세션 미들웨어 (Google OAuth에 필요)
secret_key = settings.secret_key or "default-secret-key-for-railway"
app.add_middleware(SessionMiddleware, secret_key=secret_key)
logger.info("Session middleware configured")

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
    logger.info("Initializing database...")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """메인 페이지"""
    return templates.TemplateResponse("index.html", {"request": request})
