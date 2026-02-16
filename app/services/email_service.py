import random
import string
from datetime import timedelta
from app.database import utc_now
from aiosmtplib import SMTP
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings


def generate_verification_code(length: int = 6) -> str:
    """6자리 숫자 인증코드 생성"""
    return ''.join(random.choices(string.digits, k=length))


async def send_verification_email(to_email: str, code: str) -> bool:
    """이메일로 인증코드 발송"""

    # 테스트용 도메인은 실제 발송하지 않음
    test_domains = {"example.com", "example.org", "example.net", "test.com"}
    domain = to_email.split("@")[-1].lower() if "@" in to_email else ""
    if domain in test_domains:
        print(f"[TEST] 테스트 도메인 발송 스킵: {to_email} -> {code}")
        return True

    # SMTP 설정이 없으면 콘솔에 출력 (개발용)
    if not settings.smtp_host or not settings.smtp_username:
        print(f"[DEV] 인증코드 발송: {to_email} -> {code}")
        return True

    try:
        message = MIMEMultipart("alternative")
        message["From"] = settings.smtp_from_email
        message["To"] = to_email
        message["Subject"] = "[Contract Sync] 이메일 인증코드"

        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: #f9f9f9; padding: 30px; border-radius: 10px;">
                <h2 style="color: #333; text-align: center;">Contract Sync 이메일 인증</h2>
                <p style="color: #666; text-align: center;">아래 인증코드를 입력하여 이메일 인증을 완료하세요.</p>
                <div style="background: #4F46E5; color: white; font-size: 32px; font-weight: bold; text-align: center; padding: 20px; border-radius: 8px; letter-spacing: 8px; margin: 20px 0;">
                    {code}
                </div>
                <p style="color: #999; text-align: center; font-size: 14px;">이 인증코드는 10분간 유효합니다.</p>
            </div>
        </body>
        </html>
        """

        message.attach(MIMEText(html_content, "html"))

        async with SMTP(
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=settings.smtp_use_tls,
            username=settings.smtp_username,
            password=settings.smtp_password
        ) as smtp:
            await smtp.send_message(message)

        return True
    except Exception as e:
        print(f"이메일 발송 실패: {e}")
        return False


def get_code_expiry():
    """인증코드 만료시간 (10분 후)"""
    return utc_now() + timedelta(minutes=10)
