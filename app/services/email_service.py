import asyncio
import os
import random
import string
import logging
from datetime import timedelta

from aiosmtplib import SMTP
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader

from app.database import utc_now
from app.config import settings

logger = logging.getLogger(__name__)

# ── Jinja2 템플릿 환경 ──

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates", "email")
_template_env = Environment(
    loader=FileSystemLoader(os.path.abspath(_TEMPLATE_DIR)),
    autoescape=True,
)

# 테스트 도메인 (실제 발송 스킵)
_TEST_DOMAINS = {"example.com", "example.org", "example.net", "test.com", "localhost"}


def generate_verification_code(length: int = 6) -> str:
    """6자리 숫자 인증코드 생성"""
    return ''.join(random.choices(string.digits, k=length))


async def send_verification_email(to_email: str, code: str) -> bool:
    """이메일로 인증코드 발송"""

    # 테스트용 도메인은 실제 발송하지 않음
    domain = to_email.split("@")[-1].lower() if "@" in to_email else ""
    if domain in _TEST_DOMAINS:
        # H-2: 인증코드를 로그에 노출하지 않음
        logger.debug(f"테스트 도메인 발송 스킵: {to_email}")
        return True

    # SMTP 설정이 없으면 개발 모드 (코드 노출 방지)
    if not settings.smtp_host or not settings.smtp_username:
        # H-2: 인증코드 값을 로그에 노출하지 않음
        logger.info(f"[DEV] SMTP 미설정 - 인증코드 발송 시뮬레이션: {to_email}")
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

        # M-13: SMTP 타임아웃 설정 (30초)
        async with SMTP(
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=settings.smtp_use_tls,
            username=settings.smtp_username,
            password=settings.smtp_password,
            timeout=30,
        ) as smtp:
            await smtp.send_message(message)

        return True
    except Exception as e:
        # H-2: logger 사용 (print 대신)
        logger.error(f"이메일 발송 실패: {e}")
        return False


def get_code_expiry():
    """인증코드 만료시간 (10분 후)"""
    return utc_now() + timedelta(minutes=10)


# ── 범용 이메일 발송 ──

def _render_template(template_name: str, context: dict) -> str:
    """Jinja2 이메일 템플릿 렌더링"""
    template = _template_env.get_template(template_name)
    return template.render(**context)


def _is_test_recipient(email: str) -> bool:
    """테스트 도메인 여부 확인"""
    domain = email.split("@")[-1].lower() if "@" in email else ""
    return domain in _TEST_DOMAINS


async def _send_email(
    to_emails: list[str],
    subject: str,
    html_body: str,
    cc_emails: list[str] | None = None,
) -> bool:
    """범용 이메일 발송 (단일 시도)"""
    # 모든 수신자가 테스트 도메인이면 스킵
    all_recipients = list(to_emails) + (cc_emails or [])
    if all(_is_test_recipient(e) for e in all_recipients):
        logger.debug(f"테스트 도메인 발송 스킵: {all_recipients}")
        return True

    # SMTP 미설정 → 개발 모드
    if not settings.smtp_host or not settings.smtp_username:
        logger.info(f"[DEV] SMTP 미설정 - 이메일 발송 시뮬레이션: to={to_emails}, subject={subject}")
        return True

    try:
        message = MIMEMultipart("alternative")
        message["From"] = settings.smtp_from_email
        message["To"] = ", ".join(to_emails)
        message["Subject"] = subject
        if cc_emails:
            message["Cc"] = ", ".join(cc_emails)

        message.attach(MIMEText(html_body, "html", "utf-8"))

        recipients = list(to_emails)
        if cc_emails:
            recipients.extend(cc_emails)

        async with SMTP(
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=settings.smtp_use_tls,
            username=settings.smtp_username,
            password=settings.smtp_password,
            timeout=30,
        ) as smtp:
            await smtp.send_message(message, recipients=recipients)

        logger.info(f"이메일 발송 성공: to={to_emails}, subject={subject}")
        return True
    except Exception as e:
        logger.error(f"이메일 발송 실패: to={to_emails}, error={e}")
        return False


async def send_email_with_retry(
    to_emails: list[str],
    subject: str,
    html_body: str,
    cc_emails: list[str] | None = None,
    max_retries: int = 3,
    base_interval: int = 10,
) -> bool:
    """재시도 로직 포함 이메일 발송 (지수 백오프: 10s → 30s → 90s, 최대 ~2분)"""
    for attempt in range(max_retries):
        success = await _send_email(to_emails, subject, html_body, cc_emails)
        if success:
            return True
        if attempt < max_retries - 1:
            wait = base_interval * (3 ** attempt)  # 10, 30, 90
            logger.warning(f"이메일 재시도 {attempt + 1}/{max_retries}, {wait}초 후 재시도")
            await asyncio.sleep(wait)
    logger.error(f"이메일 최종 발송 실패 ({max_retries}회): to={to_emails}")
    return False


# ── 완료 보고 이메일 ──

async def send_completion_report_email(
    recipient_email: str,
    cc_emails: list[str] | None,
    subject: str,
    project_name: str,
    task_name: str,
    sender_name: str,
    body_content: str,
    feedback_url: str,
) -> bool:
    """완료 보고 이메일 발송 (completion_report.html 템플릿)"""
    html_body = _render_template("completion_report.html", {
        "project_name": project_name,
        "task_name": task_name,
        "sender_name": sender_name,
        "body_content": body_content,
        "feedback_url": feedback_url,
    })
    return await send_email_with_retry(
        to_emails=[recipient_email],
        subject=subject,
        html_body=html_body,
        cc_emails=cc_emails,
    )


# ── 피드백 리마인더 이메일 ──

async def send_feedback_reminder_email(
    recipient_email: str,
    project_name: str,
    task_name: str,
    sender_name: str,
    auto_confirm_date: str,
    feedback_url: str,
) -> bool:
    """피드백 리마인더 이메일 발송 (feedback_reminder.html 템플릿)"""
    html_body = _render_template("feedback_reminder.html", {
        "project_name": project_name,
        "task_name": task_name,
        "sender_name": sender_name,
        "auto_confirm_date": auto_confirm_date,
        "feedback_url": feedback_url,
    })
    return await send_email_with_retry(
        to_emails=[recipient_email],
        subject=f"[리마인더] '{task_name}' 완료 확인을 요청드립니다",
        html_body=html_body,
    )
