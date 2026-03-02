from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """애플리케이션 설정"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google Gemini
    gemini_api_key: str = ""

    # App
    debug: bool = False  # M-7: 프로덕션 기본값 False
    max_file_size_mb: int = 50
    secret_key: str = ""  # C-2: 빈 문자열 기본값 (프로덕션에서 반드시 설정 필요)

    # Paths
    upload_dir: str = "uploads"
    data_dir: str = ""  # Railway Volume 마운트 경로 (예: /data). 비어있으면 프로젝트 루트 사용

    # CORS 허용 도메인 (쉼표 구분 문자열, 비어있으면 debug 시 전체 허용)
    allowed_origins: str = ""

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # 이메일 발송 (Resend HTTP API 우선, SMTP 폴백)
    resend_api_key: str = ""  # Resend API 키 (Railway 등 SMTP 차단 환경용)
    resend_from_email: str = "Contract Sync <onboarding@resend.dev>"  # Resend 발신자

    # SMTP (이메일 발송) — Resend 미설정 시 폴백
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
