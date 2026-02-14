from contextlib import asynccontextmanager
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행되는 lifespan 핸들러"""
    logger.info("Initializing database...")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    yield


app = FastAPI(
    title="Contract Sync",
    description="외주용역 계약서에서 추진 일정을 추출하고 업무 목록을 생성하는 API",
    version="1.0.0",
    lifespan=lifespan,
)

# 세션 미들웨어 (Google OAuth에 필요)
if not settings.secret_key or settings.secret_key == "your-secret-key-change-in-production":
    logger.warning("SECRET_KEY가 설정되지 않았습니다. 프로덕션에서는 반드시 변경하세요.")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
logger.info("Session middleware configured")

# CORS 설정 - 프로덕션에서는 실제 도메인만 허용
allowed_origins = settings.allowed_origins if settings.allowed_origins else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
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


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """메인 페이지"""
    return templates.TemplateResponse("index.html", {"request": request})
