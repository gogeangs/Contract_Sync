"""카카오 알림톡 발송 서비스 — 3차 개발 S6-3, S6-5 (선택)

딜러사 API 연동 + 발송 이력 저장
현재 구현: 인터페이스 + 로깅 (실제 딜러사 계약 전 준비 단계)
"""
import logging
from datetime import timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import KakaoNotification, utc_now

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 알림톡 템플릿 코드 (P-10)
TEMPLATES = {
    "feedback_request": {
        "code": "CS_FEEDBACK_001",
        "title": "시안 확인 요청",
        "body": "#{고객명}님, #{회사명}에서 #{프로젝트명} 시안 확인을 요청드립니다. 아래 링크에서 확인해주세요.\n#{포털링크}",
        "buttons": [{"type": "WL", "name": "시안 확인하기", "url_mobile": "#{포털링크}"}],
    },
    "feedback_reminder": {
        "code": "CS_REMINDER_001",
        "title": "시안 확인 리마인드",
        "body": "#{고객명}님, #{프로젝트명} 시안 확인을 기다리고 있습니다. (경과일: #{경과일수}일)\n#{포털링크}",
        "buttons": [{"type": "WL", "name": "시안 확인하기", "url_mobile": "#{포털링크}"}],
    },
    "feedback_received": {
        "code": "CS_FEEDBACK_002",
        "title": "피드백 접수 확인",
        "body": "#{고객명}님, #{프로젝트명}에 대한 피드백이 정상적으로 접수되었습니다. 담당자가 확인 후 진행하겠습니다.",
    },
}


async def send_kakao_notification(
    db: AsyncSession,
    template_key: str,
    recipient_phone: str,
    variables: dict,
    project_id: int | None = None,
    feedback_request_id: int | None = None,
) -> KakaoNotification:
    """알림톡 발송 + 이력 저장

    Returns: KakaoNotification 레코드
    """
    template = TEMPLATES.get(template_key)
    if not template:
        raise ValueError(f"알 수 없는 템플릿: {template_key}")

    # 이력 레코드 생성
    record = KakaoNotification(
        project_id=project_id,
        feedback_request_id=feedback_request_id,
        template_code=template["code"],
        recipient_phone=recipient_phone,
        variables=variables,
        status="pending",
    )
    db.add(record)
    await db.flush()

    # 실제 발송 시도
    if settings.kakao_api_key and settings.kakao_sender_key:
        success, error = await _call_kakao_api(template, recipient_phone, variables)
        if success:
            record.status = "sent"
            record.sent_at = utc_now()
        else:
            record.status = "failed"
            record.error_message = error
    else:
        # 딜러사 API 미설정 — 개발 모드 로깅
        logger.info(f"[알림톡 DEV] template={template_key}, phone={recipient_phone}, vars={variables}")
        record.status = "sent"  # 개발 모드에서는 성공 처리
        record.sent_at = utc_now()

    return record


async def _call_kakao_api(
    template: dict,
    recipient_phone: str,
    variables: dict,
) -> tuple[bool, str | None]:
    """딜러사 API 호출 (실제 연동 시 구현)

    현재는 placeholder — 딜러사 선정 후 실제 API 규격에 맞춰 구현
    """
    try:
        # TODO: 딜러사 API 엔드포인트 연동
        # 예시: NHN Cloud, 인포뱅크, 비즈엠 등
        payload = {
            "senderKey": settings.kakao_sender_key,
            "templateCode": template["code"],
            "recipientNo": recipient_phone,
            "templateParameter": variables,
        }

        if template.get("buttons"):
            payload["buttons"] = template["buttons"]

        logger.info(f"[알림톡] 발송 요청: {template['code']} → {recipient_phone}")

        # async with httpx.AsyncClient(timeout=10) as client:
        #     resp = await client.post(
        #         "https://api-alimtalk.dealer.com/v2/send",
        #         headers={"Authorization": f"Bearer {settings.kakao_api_key}"},
        #         json=payload,
        #     )
        #     if resp.status_code == 200:
        #         return True, None
        #     return False, resp.text[:200]

        return True, None  # placeholder

    except Exception as e:
        logger.error(f"알림톡 API 호출 실패: {e}")
        return False, str(e)


async def get_notification_history(
    db: AsyncSession,
    project_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """알림톡 발송 이력 조회"""
    q = select(KakaoNotification).order_by(KakaoNotification.created_at.desc()).limit(limit)
    if project_id:
        q = q.where(KakaoNotification.project_id == project_id)

    result = await db.execute(q)
    return [{
        "id": n.id,
        "project_id": n.project_id,
        "template_code": n.template_code,
        "recipient_phone": n.recipient_phone,
        "status": n.status,
        "error_message": n.error_message,
        "sent_at": n.sent_at.isoformat() if n.sent_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    } for n in result.scalars().all()]
