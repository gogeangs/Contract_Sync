import asyncio
import os
import random
import string
import logging
from datetime import timedelta

import httpx
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


# ══════════════════════════════════════════
#  Resend HTTP API (Railway 등 SMTP 차단 환경용)
# ══════════════════════════════════════════

async def _send_via_resend(
    to_emails: list[str],
    subject: str,
    html_body: str,
    cc_emails: list[str] | None = None,
) -> tuple[bool, str]:
    """Resend HTTP API로 이메일 발송"""
    print(f"[EMAIL] Resend API 발송: to={to_emails}, subject={subject}", flush=True)

    payload = {
        "from": settings.resend_from_email,
        "to": to_emails,
        "subject": subject,
        "html": html_body,
    }
    if cc_emails:
        payload["cc"] = cc_emails

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if resp.status_code == 200:
            print(f"[EMAIL] Resend 발송 성공: {resp.json()}", flush=True)
            logger.info(f"이메일 발송 성공 (Resend): to={to_emails}")
            return True, ""
        else:
            err_msg = f"Resend API {resp.status_code}: {resp.text}"
            print(f"[EMAIL] Resend 발송 실패: {err_msg}", flush=True)
            logger.error(f"이메일 발송 실패 (Resend): {err_msg}")
            return False, err_msg

    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        print(f"[EMAIL] Resend 발송 실패: {err_msg}", flush=True)
        logger.error(f"이메일 발송 실패 (Resend): {err_msg}")
        return False, err_msg


# ══════════════════════════════════════════
#  SMTP 발송 (폴백)
# ══════════════════════════════════════════

async def _send_via_smtp(
    to_emails: list[str],
    subject: str,
    html_body: str,
    cc_emails: list[str] | None = None,
) -> tuple[bool, str]:
    """SMTP로 이메일 발송"""
    port = settings.smtp_port
    host = settings.smtp_host

    if port == 465:
        use_tls, start_tls = True, False
    else:
        use_tls, start_tls = False, settings.smtp_use_tls

    print(f"[EMAIL] SMTP 발송: host={host}:{port}, to={to_emails}", flush=True)

    try:
        message = MIMEMultipart("alternative")
        message["From"] = settings.smtp_from_email
        message["To"] = ", ".join(to_emails)
        message["Subject"] = subject
        if cc_emails:
            message["Cc"] = ", ".join(cc_emails)
        message.attach(MIMEText(html_body, "html", "utf-8"))

        recipients = list(to_emails) + (cc_emails or [])

        smtp = SMTP(hostname=host, port=port, use_tls=use_tls, start_tls=start_tls, timeout=15)
        await smtp.connect()
        await smtp.login(settings.smtp_username, settings.smtp_password)
        await smtp.send_message(message, recipients=recipients)
        await smtp.quit()

        print("[EMAIL] SMTP 발송 성공", flush=True)
        logger.info(f"이메일 발송 성공 (SMTP): to={to_emails}")
        return True, ""

    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        print(f"[EMAIL] SMTP 발송 실패: {err_msg}", flush=True)
        logger.error(f"이메일 발송 실패 (SMTP): {err_msg}")
        return False, err_msg


# ══════════════════════════════════════════
#  통합 발송 (Resend 우선 → SMTP 폴백 → 개발 모드)
# ══════════════════════════════════════════

def _is_test_recipient(email: str) -> bool:
    """테스트 도메인 여부 확인"""
    domain = email.split("@")[-1].lower() if "@" in email else ""
    return domain in _TEST_DOMAINS


async def _send_email(
    to_emails: list[str],
    subject: str,
    html_body: str,
    cc_emails: list[str] | None = None,
) -> tuple[bool, str]:
    """통합 이메일 발송 (Resend → SMTP → 개발모드)"""
    # 테스트 도메인 스킵
    all_recipients = list(to_emails) + (cc_emails or [])
    if all(_is_test_recipient(e) for e in all_recipients):
        logger.debug(f"테스트 도메인 발송 스킵: {all_recipients}")
        return True, ""

    # 1) Resend API (우선)
    if settings.resend_api_key:
        return await _send_via_resend(to_emails, subject, html_body, cc_emails)

    # 2) SMTP (폴백)
    if settings.smtp_host and settings.smtp_username:
        return await _send_via_smtp(to_emails, subject, html_body, cc_emails)

    # 3) 개발 모드
    logger.info(f"[DEV] 이메일 미설정 - 발송 시뮬레이션: to={to_emails}, subject={subject}")
    return True, ""


async def send_verification_email(to_email: str, code: str) -> tuple[bool, str]:
    """이메일로 인증코드 발송. (성공여부, 에러메시지) 반환"""

    domain = to_email.split("@")[-1].lower() if "@" in to_email else ""
    if domain in _TEST_DOMAINS:
        return True, ""

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

    return await _send_email(
        to_emails=[to_email],
        subject="[Contract Sync] 이메일 인증코드",
        html_body=html_content,
    )


def get_code_expiry():
    """인증코드 만료시간 (10분 후)"""
    return utc_now() + timedelta(minutes=10)


# ── 템플릿 렌더링 ──

def _render_template(template_name: str, context: dict) -> str:
    """Jinja2 이메일 템플릿 렌더링"""
    template = _template_env.get_template(template_name)
    return template.render(**context)


# ── 재시도 포함 발송 ──

async def send_email_with_retry(
    to_emails: list[str],
    subject: str,
    html_body: str,
    cc_emails: list[str] | None = None,
    max_retries: int = 3,
    base_interval: int = 10,
) -> bool:
    """재시도 로직 포함 이메일 발송"""
    for attempt in range(max_retries):
        success, _ = await _send_email(to_emails, subject, html_body, cc_emails)
        if success:
            return True
        if attempt < max_retries - 1:
            wait = base_interval * (3 ** attempt)
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
