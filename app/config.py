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
    debug: bool = True
    max_file_size_mb: int = 50
    secret_key: str = "your-secret-key-change-in-production"

    # Paths
    upload_dir: str = "uploads"

    # CORS 허용 도메인 (쉼표 구분, 비어있으면 모든 도메인 허용)
    allowed_origins: list[str] = []

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # SMTP (이메일 발송)
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
