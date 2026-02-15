import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.database import Base, get_db, utc_now, UserSession
from app.main import app
from app.limiter import limiter

# 테스트 중 rate limiting 비활성화
limiter.enabled = False


# 테스트용 인메모리 DB
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """각 테스트마다 테이블 생성/삭제"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client():
    """비인증 HTTP 클라이언트"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_client():
    """인증된 HTTP 클라이언트 (회원가입 + 로그인 완료)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. 인증코드 발송
        await ac.post("/api/v1/auth/send-code", json={"email": "test@example.com"})

        # 2. DB에서 인증코드 직접 조회하여 인증
        async with TestSessionLocal() as db:
            from sqlalchemy import select
            from app.database import VerificationCode
            result = await db.execute(
                select(VerificationCode).where(VerificationCode.email == "test@example.com")
            )
            code = result.scalar_one().code

        # 3. 인증코드 확인
        await ac.post("/api/v1/auth/verify-code", json={"email": "test@example.com", "code": code})

        # 4. 회원가입
        resp = await ac.post("/api/v1/auth/signup", json={
            "email": "test@example.com",
            "password": "test1234",
            "password_confirm": "test1234",
        })

        # 쿠키가 자동으로 클라이언트에 저장됨
        yield ac
