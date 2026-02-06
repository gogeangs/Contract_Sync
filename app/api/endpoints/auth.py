from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import secrets
import bcrypt

from app.config import settings
from app.database import get_db, User, VerificationCode, init_db
from app.services.email_service import generate_verification_code, send_verification_email, get_code_expiry

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

# 간단한 세션 저장소 (프로덕션에서는 Redis 등 사용)
sessions = {}


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
async def send_verification_code(data: SendCodeRequest, db: AsyncSession = Depends(get_db)):
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
            VerificationCode.is_used == False
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
async def verify_code(data: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    """이메일 인증코드 확인"""
    result = await db.execute(
        select(VerificationCode).where(
            VerificationCode.email == data.email,
            VerificationCode.code == data.code,
            VerificationCode.is_used == False
        )
    )
    verification = result.scalar_one_or_none()

    if not verification:
        raise HTTPException(status_code=400, detail="잘못된 인증코드입니다.")

    if verification.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="인증코드가 만료되었습니다.")

    # 코드 사용 처리
    verification.is_used = True
    await db.commit()

    return {"message": "이메일 인증이 완료되었습니다.", "verified": True}


@router.post("/signup")
async def signup(data: SignupRequest, db: AsyncSession = Depends(get_db)):
    """이메일 회원가입"""
    # 비밀번호 확인
    if data.password != data.password_confirm:
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")

    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="비밀번호는 6자 이상이어야 합니다.")

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
    session_token = secrets.token_urlsafe(32)
    sessions[session_token] = {
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'picture': user.picture
    }

    response = JSONResponse(content={"message": "회원가입이 완료되었습니다.", "success": True})
    response.set_cookie(key="session_token", value=session_token, httponly=True, max_age=86400)
    return response


@router.post("/login/email")
async def email_login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """이메일 로그인"""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    if not user.is_verified:
        raise HTTPException(status_code=401, detail="이메일 인증이 필요합니다.")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="비활성화된 계정입니다.")

    # 세션 생성
    session_token = secrets.token_urlsafe(32)
    sessions[session_token] = {
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'picture': user.picture
    }

    response = JSONResponse(content={"message": "로그인 성공", "success": True})
    response.set_cookie(key="session_token", value=session_token, httponly=True, max_age=86400)
    return response


# ============ Google OAuth API ============

@router.get("/login/google")
async def google_login(request: Request):
    """Google OAuth 로그인 시작"""
    if not settings.google_client_id:
        raise HTTPException(status_code=400, detail="Google OAuth가 설정되지 않았습니다.")

    redirect_uri = str(request.url_for('google_callback'))
    # Railway 프록시 뒤에서 http -> https 변환
    if redirect_uri.startswith('http://') and 'railway.app' in redirect_uri:
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
                password_hash="",  # Google 로그인은 비밀번호 없음
                name=user_info.get('name'),
                picture=user_info.get('picture'),
                is_verified=True,
                auth_provider="google"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        # 세션 토큰 생성
        session_token = secrets.token_urlsafe(32)
        sessions[session_token] = {
            'id': user.id,
            'email': user.email,
            'name': user.name or user_info.get('name'),
            'picture': user.picture or user_info.get('picture')
        }

        # 메인 페이지로 리다이렉트
        response = RedirectResponse(url="/")
        response.set_cookie(key="session_token", value=session_token, httponly=True, max_age=86400)
        return response

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"로그인 실패: {str(e)}")


# ============ 공통 API ============

@router.get("/me")
async def get_current_user(request: Request):
    """현재 로그인한 사용자 정보"""
    session_token = request.cookies.get("session_token")

    if not session_token or session_token not in sessions:
        return {"logged_in": False, "user": None}

    return {"logged_in": True, "user": sessions[session_token]}


@router.post("/logout")
async def logout(request: Request):
    """로그아웃"""
    session_token = request.cookies.get("session_token")

    if session_token and session_token in sessions:
        del sessions[session_token]

    response = JSONResponse(content={"message": "로그아웃 되었습니다."})
    response.delete_cookie(key="session_token")
    return response
