from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
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
from app.database import init_db, async_session, UserSession, utc_now
from app.limiter import limiter

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

        # 만료된 세션 정리
        async with async_session() as db:
            from sqlalchemy import delete
            result = await db.execute(
                delete(UserSession).where(UserSession.expires_at < utc_now())
            )
            if result.rowcount:
                await db.commit()
                logger.info(f"Cleaned up {result.rowcount} expired sessions")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    # L-8: 주기적 만료 세션 정리 (1시간 간격)
    import asyncio

    async def _cleanup_expired_sessions():
        while True:
            await asyncio.sleep(3600)
            try:
                async with async_session() as db:
                    from sqlalchemy import delete as _del
                    r = await db.execute(
                        _del(UserSession).where(UserSession.expires_at < utc_now())
                    )
                    if r.rowcount:
                        await db.commit()
                        logger.info(f"Periodic cleanup: {r.rowcount} expired sessions removed")
            except Exception:
                pass

    cleanup_task = asyncio.create_task(_cleanup_expired_sessions())
    yield
    cleanup_task.cancel()


app = FastAPI(
    title="Contract Sync",
    description="외주용역 계약서에서 추진 일정을 추출하고 업무 목록을 생성하는 API",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate Limiter 등록
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# C-2: 프로덕션에서 SECRET_KEY 미설정 시 앱 시작 차단
if not settings.secret_key:
    import secrets as _secrets
    if settings.debug:
        _generated_key = _secrets.token_urlsafe(32)
        logger.warning(f"SECRET_KEY 미설정. 개발 모드이므로 임시 키를 생성합니다.")
        settings.secret_key = _generated_key
    else:
        raise RuntimeError("SECRET_KEY가 설정되지 않았습니다. 환경변수 SECRET_KEY를 설정하세요.")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
logger.info("Session middleware configured")

# H-1: CORS 설정 - 프로덕션에서는 와일드카드 차단
if settings.allowed_origins:
    allowed_origins = settings.allowed_origins
elif settings.debug:
    allowed_origins = ["*"]
    logger.warning("개발 모드: CORS 모든 도메인 허용. 프로덕션에서는 ALLOWED_ORIGINS를 설정하세요.")
else:
    allowed_origins = []
    logger.warning("ALLOWED_ORIGINS가 설정되지 않았습니다. CORS가 차단됩니다.")
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
