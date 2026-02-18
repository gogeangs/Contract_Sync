from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import secrets
import bcrypt
import logging

from app.config import settings
from app.database import get_db, User, VerificationCode, UserSession, Team, TeamMember, init_db, utc_now
from app.limiter import limiter

from app.services.email_service import generate_verification_code, send_verification_email, get_code_expiry

logger = logging.getLogger(__name__)

router = APIRouter()

# OAuth 설정
oauth = OAuth()

# Google OAuth 등록
if settings.google_client_id and settings.google_client_secret:
    oauth.register(
        name='google',
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

SESSION_MAX_AGE = 86400  # 24시간


def _set_session_cookie(response: JSONResponse | RedirectResponse, session_token: str):
    """세션 쿠키 설정 (보안 플래그 포함)"""
    is_production = not settings.debug
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=SESSION_MAX_AGE,
        secure=is_production,
        samesite="lax",
    )


async def _create_session(db: AsyncSession, user: User) -> str:
    """DB에 세션 생성하고 토큰 반환"""
    from datetime import timedelta
    session_token = secrets.token_urlsafe(32)
    session = UserSession(
        token=session_token,
        user_id=user.id,
        expires_at=utc_now() + timedelta(seconds=SESSION_MAX_AGE),
    )
    db.add(session)
    await db.commit()
    return session_token


# Pydantic 모델
class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    password_confirm: str


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SendCodeRequest(BaseModel):
    email: EmailStr


# 비밀번호 해싱
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


# ============ 이메일 회원가입 API ============

@router.post("/send-code")
@limiter.limit("5/minute")
async def send_verification_code(request: Request, data: SendCodeRequest, db: AsyncSession = Depends(get_db)):
    """이메일 인증코드 발송"""
    # 이미 가입된 이메일인지 확인
    result = await db.execute(select(User).where(User.email == data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user and existing_user.is_verified:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다.")

    # 인증코드 생성
    code = generate_verification_code()
    expires_at = get_code_expiry()

    # 기존 미사용 코드 삭제
    await db.execute(
        VerificationCode.__table__.delete().where(
            VerificationCode.email == data.email,
            VerificationCode.is_used.is_(False)
        )
    )

    # 새 인증코드 저장
    verification = VerificationCode(
        email=data.email,
        code=code,
        expires_at=expires_at
    )
    db.add(verification)
    await db.commit()

    # 이메일 발송
    sent = await send_verification_email(data.email, code)
    if not sent:
        raise HTTPException(status_code=500, detail="이메일 발송에 실패했습니다.")

    # SMTP 미설정시 (개발 모드) 인증코드를 응답에 포함
    response = {"message": "인증코드가 발송되었습니다.", "email": data.email}
    if not settings.smtp_host:
        response["dev_code"] = code
        response["message"] = f"[개발모드] 인증코드: {code}"

    return response


@router.post("/verify-code")
@limiter.limit("5/minute")
async def verify_code(request: Request, data: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    """이메일 인증코드 확인"""
    result = await db.execute(
        select(VerificationCode).where(
            VerificationCode.email == data.email,
            VerificationCode.code == data.code,
            VerificationCode.is_used.is_(False)
        )
    )
    verification = result.scalar_one_or_none()

    if not verification:
        raise HTTPException(status_code=400, detail="잘못된 인증코드입니다.")

    if verification.expires_at < utc_now():
        raise HTTPException(status_code=400, detail="인증코드가 만료되었습니다.")

    # 코드 사용 처리
    verification.is_used = True
    await db.commit()

    return {"message": "이메일 인증이 완료되었습니다.", "verified": True}


@router.post("/signup")
@limiter.limit("3/minute")
async def signup(request: Request, data: SignupRequest, db: AsyncSession = Depends(get_db)):
    """이메일 회원가입"""
    # 비밀번호 확인
    if data.password != data.password_confirm:
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")

    # M-6: 비밀번호 복잡도 강화
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다.")
    import re as _re
    if not _re.search(r'[A-Za-z]', data.password) or not _re.search(r'\d', data.password):
        raise HTTPException(status_code=400, detail="비밀번호는 영문자와 숫자를 모두 포함해야 합니다.")

    # 이메일 인증 확인
    result = await db.execute(
        select(VerificationCode).where(
            VerificationCode.email == data.email,
            VerificationCode.is_used == True
        )
    )
    verified = result.scalar_one_or_none()

    if not verified:
        raise HTTPException(status_code=400, detail="이메일 인증이 필요합니다.")

    # 이미 가입된 이메일인지 확인
    result = await db.execute(select(User).where(User.email == data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다.")

    # 사용자 생성
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        is_verified=True,
        auth_provider="email"
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 세션 생성 및 자동 로그인
    session_token = await _create_session(db, user)

    response = JSONResponse(content={"message": "회원가입이 완료되었습니다.", "success": True})
    _set_session_cookie(response, session_token)
    return response


@router.post("/login/email")
@limiter.limit("3/minute")
async def email_login(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """이메일 로그인"""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    # H-7: 타이밍 공격 방지 - 사용자 존재 여부와 무관하게 항상 bcrypt 검증 수행
    _dummy_hash = "$2b$12$LJ3m4ys3Lg2HEOyMKiJYuuGzOJfCqyYBGmMcVDFmJGNFkXMzGq.ZC"
    password_valid = verify_password(data.password, user.password_hash if (user and user.password_hash) else _dummy_hash)
    if not user or not user.password_hash or not password_valid:
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    if not user.is_verified:
        raise HTTPException(status_code=401, detail="이메일 인증이 필요합니다.")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="비활성화된 계정입니다.")

    # 세션 생성
    session_token = await _create_session(db, user)

    response = JSONResponse(content={"message": "로그인 성공", "success": True})
    _set_session_cookie(response, session_token)
    return response


# ============ Google OAuth API ============

@router.get("/login/google")
async def google_login(request: Request):
    """Google OAuth 로그인 시작"""
    if not settings.google_client_id:
        raise HTTPException(status_code=400, detail="Google OAuth가 설정되지 않았습니다.")

    redirect_uri = str(request.url_for('google_callback'))
    # 프록시 뒤에서 http -> https 변환 (X-Forwarded-Proto 우선)
    proto = request.headers.get("X-Forwarded-Proto", request.url.scheme)
    if proto == "https" and redirect_uri.startswith('http://'):
        redirect_uri = redirect_uri.replace('http://', 'https://', 1)
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback/google")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """Google OAuth 콜백"""
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')

        if not user_info:
            raise HTTPException(status_code=400, detail="사용자 정보를 가져올 수 없습니다.")

        email = user_info.get('email')

        # DB에서 사용자 확인 또는 생성
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            # 새 사용자 생성
            user = User(
                email=email,
                password_hash=None,  # Google 로그인은 비밀번호 없음
                name=user_info.get('name'),
                picture=user_info.get('picture'),
                is_verified=True,
                auth_provider="google"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        # 세션 토큰 생성
        session_token = await _create_session(db, user)

        # 메인 페이지로 리다이렉트
        response = RedirectResponse(url="/")
        _set_session_cookie(response, session_token)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google OAuth 콜백 에러: {type(e).__name__}: {e}")
        raise HTTPException(status_code=400, detail="Google 로그인 처리 중 오류가 발생했습니다.")


# ============ 공통 인증 의존성 ============

async def require_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """세션에서 현재 로그인된 사용자 가져오기 (의존성 주입용)"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    # DB에서 세션 조회
    result = await db.execute(
        select(UserSession).where(UserSession.token == session_token)
    )
    session = result.scalar_one_or_none()

    if not session or session.expires_at < utc_now():
        # 만료된 세션 삭제
        if session:
            await db.delete(session)
            await db.commit()
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    result = await db.execute(select(User).where(User.id == session.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")

    return user


# ============ 공통 API ============

@router.get("/me")
async def get_me(request: Request, db: AsyncSession = Depends(get_db)):
    """현재 로그인한 사용자 정보"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        return {"logged_in": False, "user": None}

    result = await db.execute(
        select(UserSession).where(UserSession.token == session_token)
    )
    session = result.scalar_one_or_none()

    if not session or session.expires_at < utc_now():
        return {"logged_in": False, "user": None}

    result = await db.execute(select(User).where(User.id == session.user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"logged_in": False, "user": None}

    # 팀 목록 조회
    teams_result = await db.execute(
        select(Team, TeamMember.role)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id)
        .order_by(Team.created_at)
    )
    teams = [
        {"id": team.id, "name": team.name, "role": role}
        for team, role in teams_result.all()
    ]

    return {
        "logged_in": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
        },
        "teams": teams,
    }


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    """로그아웃"""
    session_token = request.cookies.get("session_token")

    if session_token:
        result = await db.execute(
            select(UserSession).where(UserSession.token == session_token)
        )
        session = result.scalar_one_or_none()
        if session:
            await db.delete(session)
            await db.commit()

    response = JSONResponse(content={"message": "로그아웃 되었습니다."})
    is_production = not settings.debug
    response.delete_cookie(
        key="session_token",
        path="/",
        secure=is_production,
        samesite="lax",
    )
    return response
