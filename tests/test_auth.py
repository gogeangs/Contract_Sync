import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_health_check(client):
    """헬스체크 엔드포인트"""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_send_code(client):
    """인증코드 발송"""
    resp = await client.post("/api/v1/auth/send-code", json={"email": "new@example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert "인증코드" in data["message"] or "dev_code" in data


@pytest.mark.asyncio
async def test_verify_code_invalid(client):
    """잘못된 인증코드"""
    resp = await client.post("/api/v1/auth/verify-code", json={"email": "x@x.com", "code": "000000"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_signup_flow(client):
    """회원가입 전체 플로우"""
    # 1. 인증코드 발송
    resp = await client.post("/api/v1/auth/send-code", json={"email": "signup@test.com"})
    assert resp.status_code == 200

    # 2. DB에서 코드 조회
    from tests.conftest import TestSessionLocal
    from sqlalchemy import select
    from app.database import VerificationCode
    async with TestSessionLocal() as db:
        result = await db.execute(
            select(VerificationCode).where(VerificationCode.email == "signup@test.com")
        )
        code = result.scalar_one().code

    # 3. 인증코드 확인
    resp = await client.post("/api/v1/auth/verify-code", json={"email": "signup@test.com", "code": code})
    assert resp.status_code == 200
    assert resp.json()["verified"] is True

    # 4. 회원가입
    resp = await client.post("/api/v1/auth/signup", json={
        "email": "signup@test.com",
        "password": "password123",
        "password_confirm": "password123",
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert "session_token" in resp.cookies


@pytest.mark.asyncio
async def test_signup_password_mismatch(client):
    """비밀번호 불일치"""
    resp = await client.post("/api/v1/auth/signup", json={
        "email": "x@x.com",
        "password": "aaa111",
        "password_confirm": "bbb222",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_signup_short_password(client):
    """짧은 비밀번호"""
    resp = await client.post("/api/v1/auth/signup", json={
        "email": "x@x.com",
        "password": "abc",
        "password_confirm": "abc",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_login_email(auth_client):
    """이메일 로그인"""
    # auth_client는 이미 회원가입 완료된 상태
    # 새 클라이언트로 로그인 테스트
    resp = await auth_client.post("/api/v1/auth/login/email", json={
        "email": "test@example.com",
        "password": "test1234",
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_login_wrong_password(auth_client):
    """잘못된 비밀번호"""
    resp = await auth_client.post("/api/v1/auth/login/email", json={
        "email": "test@example.com",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_authenticated(auth_client):
    """인증된 사용자 정보 조회"""
    resp = await auth_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["logged_in"] is True
    assert data["user"]["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_me_unauthenticated(client):
    """미인증 사용자 정보 조회"""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["logged_in"] is False


@pytest.mark.asyncio
async def test_logout(auth_client):
    """로그아웃"""
    resp = await auth_client.post("/api/v1/auth/logout")
    assert resp.status_code == 200

    # 로그아웃 후 /me 확인
    resp = await auth_client.get("/api/v1/auth/me")
    assert resp.json()["logged_in"] is False
