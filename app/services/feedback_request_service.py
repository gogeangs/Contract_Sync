"""고객 피드백 요청 서비스 — 3차 개발 S4-1 ~ S4-5

피드백 요청 생성 + 이메일 발송 + 포털 조회 + 피드백 처리 + 리마인더
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    FeedbackRequest, FeedbackResponse, Project, Client, User,
    Task, Notification, utc_now,
)
from app.services.common import log_activity

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 리마인더 정책 (P-7 §7.1)
REMINDER_SCHEDULE = [3, 3, 5]  # 영업일 간격: 1차(3일), 2차(3일), 3차(5일)
MAX_REMINDERS = 3


def _generate_feedback_token() -> str:
    """64자 무작위 토큰 생성"""
    return secrets.token_urlsafe(48)[:64]


def _count_business_days(start_date: datetime, end_date: datetime) -> int:
    """영업일 수 계산 (월~금)"""
    days = 0
    current = start_date.date()
    end = end_date.date()
    while current < end:
        if current.weekday() < 5:  # 월~금
            days += 1
        current += timedelta(days=1)
    return days


def _add_business_days(start_date: datetime, business_days: int) -> datetime:
    """시작일로부터 N 영업일 후 날짜 반환"""
    current = start_date
    added = 0
    while added < business_days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


# ══════════════════════════════════════════
#  피드백 요청 생성 (S4-1)
# ══════════════════════════════════════════

async def create_feedback_request(
    db: AsyncSession,
    user: User,
    project_id: int,
    recipient_email: str,
    subject: str,
    message: str | None = None,
    figma_url: str | None = None,
    feedback_deadline: str | None = None,
    attachments: list | None = None,
) -> FeedbackRequest:
    """피드백 요청 생성 + 이메일 발송"""
    project = await db.get(Project, project_id)
    if not project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    token = _generate_feedback_token()

    fb_request = FeedbackRequest(
        project_id=project_id,
        sender_id=user.id,
        recipient_email=recipient_email,
        subject=subject,
        message=message,
        figma_url=figma_url,
        feedback_token=token,
        feedback_deadline=feedback_deadline,
        attachments=attachments,
        status="sent",
    )
    db.add(fb_request)
    await db.flush()

    # 이메일 발송 (백그라운드)
    try:
        await _send_feedback_request_email(db, fb_request, project, user)
    except Exception as e:
        logger.error(f"피드백 요청 이메일 발송 실패: {e}")

    await log_activity(
        db, user.id, "send", "feedback_request",
        f"피드백 요청: {subject}",
        project_id=project_id, team_id=project.team_id,
    )

    await db.commit()
    return fb_request


async def _send_feedback_request_email(
    db: AsyncSession,
    fb_request: FeedbackRequest,
    project: Project,
    sender: User,
):
    """피드백 요청 이메일 발송 (P-6 §6.1)"""
    from app.services.email_service import send_email

    # 발주처 담당자 이름 조회
    client_name = "고객"
    if project.client_id:
        client = await db.get(Client, project.client_id)
        if client and client.contact_name:
            client_name = client.contact_name

    company_name = "IT솔루션"
    portal_url = f"/api/v1/feedback/portal/{fb_request.feedback_token}"
    deadline_text = fb_request.feedback_deadline or "가능한 빠른 시일 내"

    html_body = f"""
    <div style="font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <p>안녕하세요, {client_name}님.</p>
        <p>{company_name}의 {sender.name or sender.email}입니다.</p>
        <p>{project.project_name} 프로젝트의 시안이 완성되어 확인을 요청드립니다.</p>

        <hr style="border: 1px solid #e5e7eb; margin: 20px 0;">

        <p><strong>📋 요청 정보</strong></p>
        <ul style="list-style: none; padding-left: 0;">
            <li>• 프로젝트: {project.project_name}</li>
            <li>• 요청 내용: {fb_request.message or '시안 확인 부탁드립니다.'}</li>
            <li>• 응답 기한: {deadline_text}</li>
        </ul>

        <hr style="border: 1px solid #e5e7eb; margin: 20px 0;">

        <p>아래 버튼을 클릭하여 시안을 확인하고 피드백을 남겨주세요.</p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{portal_url}" style="background-color: #3b82f6; color: white; padding: 12px 32px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                시안 확인하기 →
            </a>
        </div>

        <hr style="border: 1px solid #e5e7eb; margin: 20px 0;">
        <p style="color: #6b7280; font-size: 13px;">
            본 메일은 {company_name}의 프로젝트 관리 시스템에서 자동 발송되었습니다.<br>
            문의사항이 있으시면 {sender.name or ''} ({sender.email})에게 연락해주세요.
        </p>
    </div>
    """

    email_subject = f"[{company_name}] {project.project_name} 시안이 완성되었습니다 — 확인 부탁드립니다"

    await send_email(
        to_emails=[fb_request.recipient_email],
        subject=email_subject,
        html_body=html_body,
    )


# ══════════════════════════════════════════
#  포털 조회 + 피드백 제출 (S4-3, S4-4)
# ══════════════════════════════════════════

async def get_portal_data(db: AsyncSession, token: str) -> dict | None:
    """포털 토큰으로 피드백 요청 조회 (비로그인)"""
    result = await db.execute(
        select(FeedbackRequest).where(FeedbackRequest.feedback_token == token)
    )
    fb_request = result.scalar_one_or_none()
    if not fb_request:
        return None

    if fb_request.status == "expired":
        return {"error": "이 피드백 요청은 만료되었습니다."}

    # 열람 표시
    if not fb_request.viewed_at:
        fb_request.viewed_at = utc_now()
        if fb_request.status == "sent":
            fb_request.status = "viewed"
        await db.commit()

        # PM에게 열람 알림
        db.add(Notification(
            user_id=fb_request.sender_id,
            type="feedback_viewed",
            title="고객이 시안을 열람했습니다",
            message=f"피드백 요청 '{fb_request.subject}'이 열람되었습니다.",
            link=f"#/projects/{fb_request.project_id}?tab=feedback",
        ))
        await db.commit()

    project = await db.get(Project, fb_request.project_id)
    sender = await db.get(User, fb_request.sender_id)

    # 발주처 이름
    client_name = None
    if project and project.client_id:
        client = await db.get(Client, project.client_id)
        client_name = client.name if client else None

    return {
        "project_name": project.project_name if project else "알 수 없는 프로젝트",
        "client_name": client_name,
        "sender_name": sender.name if sender else None,
        "sender_email": sender.email if sender else None,
        "subject": fb_request.subject,
        "message": fb_request.message,
        "figma_url": fb_request.figma_url,
        "attachments": fb_request.attachments,
        "feedback_deadline": fb_request.feedback_deadline,
        "created_at": fb_request.created_at.isoformat() if fb_request.created_at else None,
        "already_responded": fb_request.status == "responded",
    }


async def submit_feedback_response(
    db: AsyncSession,
    token: str,
    response_type: str,
    content: str | None,
    client_name: str | None,
    client_phone: str | None,
    ip_address: str | None,
) -> FeedbackResponse:
    """고객 피드백 제출 처리 (S4-4)"""
    result = await db.execute(
        select(FeedbackRequest).where(FeedbackRequest.feedback_token == token)
    )
    fb_request = result.scalar_one_or_none()
    if not fb_request:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="피드백 요청을 찾을 수 없습니다.")

    if fb_request.status == "responded":
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="이미 피드백이 제출되었습니다.")

    # 피드백 응답 저장
    fb_response = FeedbackResponse(
        feedback_request_id=fb_request.id,
        project_id=fb_request.project_id,
        response_type=response_type,
        content=content,
        client_name=client_name,
        client_phone=client_phone,
        ip_address=ip_address,
    )
    db.add(fb_response)

    # 피드백 요청 상태 업데이트
    fb_request.status = "responded"
    fb_request.responded_at = utc_now()

    # 후속 동작
    project = await db.get(Project, fb_request.project_id)

    if response_type == "approved":
        # 승인 → PM에게 알림
        db.add(Notification(
            user_id=fb_request.sender_id,
            type="feedback_received",
            title=f"[{project.project_name}] 고객 피드백 도착 (승인)",
            message="고객이 시안을 승인했습니다.",
            link=f"#/projects/{fb_request.project_id}?tab=feedback",
        ))
    elif response_type == "revision_requested":
        # 수정 요청 → Task 자동 생성 + PM 알림
        task = Task(
            project_id=fb_request.project_id,
            user_id=fb_request.sender_id,
            team_id=project.team_id if project else None,
            task_name=f"[수정 요청] {fb_request.subject}",
            description=content or "고객 수정 요청",
            status="pending",
            priority="높음",
            assignee_id=fb_request.sender_id,  # PM에게 할당
        )
        db.add(task)
        await db.flush()
        task.task_code = f"TASK-{task.id:03d}"

        db.add(Notification(
            user_id=fb_request.sender_id,
            type="feedback_received",
            title=f"[{project.project_name}] 고객 수정 요청 도착",
            message="고객이 수정을 요청했습니다. 업무가 자동 생성되었습니다.",
            link=f"#/tasks/{task.id}",
        ))
    elif response_type == "comment":
        # 의견 → PM 알림
        db.add(Notification(
            user_id=fb_request.sender_id,
            type="feedback_received",
            title=f"[{project.project_name}] 고객 의견 도착",
            message=content[:100] if content else "고객이 의견을 남겼습니다.",
            link=f"#/projects/{fb_request.project_id}?tab=feedback",
        ))

    await db.commit()

    # 수신 확인 이메일 발송
    try:
        await _send_feedback_confirmation_email(db, fb_request, fb_response, project)
    except Exception as e:
        logger.error(f"피드백 수신 확인 이메일 발송 실패: {e}")

    return fb_response


async def _send_feedback_confirmation_email(
    db: AsyncSession,
    fb_request: FeedbackRequest,
    fb_response: FeedbackResponse,
    project: Project,
):
    """피드백 수신 확인 이메일 (P-6 §6.3)"""
    from app.services.email_service import send_email

    sender = await db.get(User, fb_request.sender_id)
    company_name = "IT솔루션"

    type_labels = {
        "approved": "승인",
        "revision_requested": "수정 요청",
        "comment": "의견",
    }
    type_label = type_labels.get(fb_response.response_type, fb_response.response_type)

    html_body = f"""
    <div style="font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <p>안녕하세요, {fb_response.client_name or '고객'}님.</p>
        <p>{project.project_name}에 대한 피드백이 정상적으로 접수되었습니다.<br>
        담당자가 확인 후 진행하겠습니다.</p>

        <hr style="border: 1px solid #e5e7eb; margin: 20px 0;">
        <p><strong>📋 접수 내용</strong></p>
        <ul style="list-style: none; padding-left: 0;">
            <li>• 프로젝트: {project.project_name}</li>
            <li>• 피드백 유형: {type_label}</li>
            <li>• 접수 시각: {datetime.now(KST).strftime('%Y-%m-%d %H:%M')}</li>
        </ul>

        <hr style="border: 1px solid #e5e7eb; margin: 20px 0;">
        <p style="color: #6b7280; font-size: 13px;">
            추가 문의사항이 있으시면 {sender.name or ''} ({sender.email})에게 연락해주세요.<br><br>
            감사합니다.<br>{company_name} 드림
        </p>
    </div>
    """

    await send_email(
        to_emails=[fb_request.recipient_email],
        subject=f"[{company_name}] 피드백이 접수되었습니다 — {project.project_name}",
        html_body=html_body,
    )


# ══════════════════════════════════════════
#  리마인더 자동 발송 (S4-5, P-7)
# ══════════════════════════════════════════

async def process_feedback_reminders():
    """미응답 피드백 리마인더 자동 발송 (스케줄러에서 호출)

    매일 10:00 KST에 실행.
    영업일 기준으로 리마인더 발송 시점 판단.
    """

    async with (await _get_session()) as db:
        try:
            result = await db.execute(
                select(FeedbackRequest).where(
                    FeedbackRequest.status.in_(["sent", "viewed"]),
                    FeedbackRequest.reminder_count < MAX_REMINDERS,
                )
            )
            pending_requests = result.scalars().all()

            for fb_req in pending_requests:
                now = datetime.now(KST)

                # 마지막 발송 시점 결정 (리마인더 or 최초 요청)
                last_sent = fb_req.last_reminder_at or fb_req.created_at
                if last_sent.tzinfo is None:
                    last_sent = last_sent.replace(tzinfo=timezone.utc)

                # 다음 리마인더까지 영업일 수
                target_days = REMINDER_SCHEDULE[fb_req.reminder_count] if fb_req.reminder_count < len(REMINDER_SCHEDULE) else 5
                next_reminder_date = _add_business_days(last_sent, target_days)

                if now >= next_reminder_date.replace(tzinfo=KST if next_reminder_date.tzinfo is None else next_reminder_date.tzinfo):
                    # 리마인더 발송
                    project = await db.get(Project, fb_req.project_id)
                    sender = await db.get(User, fb_req.sender_id)
                    if not project or not sender:
                        continue

                    fb_req.reminder_count += 1
                    fb_req.last_reminder_at = utc_now()

                    # 리마인더 이메일 발송
                    await _send_reminder_email(fb_req, project, sender)

                    # PM에게 알림
                    db.add(Notification(
                        user_id=fb_req.sender_id,
                        type="feedback_reminder",
                        title=f"[{project.project_name}] 리마인더 {fb_req.reminder_count}차 발송됨",
                        message=f"고객({fb_req.recipient_email})에게 리마인더가 발송되었습니다.",
                        link=f"#/projects/{fb_req.project_id}?tab=feedback",
                    ))

                    # 최대 횟수 도달 시 에스컬레이션 알림
                    if fb_req.reminder_count >= MAX_REMINDERS:
                        db.add(Notification(
                            user_id=fb_req.sender_id,
                            type="feedback_escalation",
                            title=f"[{project.project_name}] 고객 미응답 — 직접 연락 필요",
                            message=f"리마인더 {MAX_REMINDERS}회 발송 완료. 고객({fb_req.recipient_email})에게 직접 연락해주세요.",
                            link=f"#/projects/{fb_req.project_id}?tab=feedback",
                        ))

            await db.commit()
        except Exception as e:
            logger.error(f"피드백 리마인더 처리 실패: {e}")
            await db.rollback()


async def _get_session():
    """async_session 래퍼"""
    from app.database import async_session
    return async_session()


async def _send_reminder_email(fb_req: FeedbackRequest, project: Project, sender: User):
    """리마인더 이메일 발송 (P-6 §6.2)"""
    from app.services.email_service import send_email

    company_name = "IT솔루션"
    created_date = fb_req.created_at.strftime("%Y-%m-%d") if fb_req.created_at else "알 수 없음"

    # 발주처 담당자 이름
    client_name = "고객"

    now_kst = datetime.now(KST)
    if fb_req.created_at:
        elapsed = (now_kst.date() - fb_req.created_at.date()).days
    else:
        elapsed = 0

    portal_url = f"/api/v1/feedback/portal/{fb_req.feedback_token}"

    html_body = f"""
    <div style="font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <p>안녕하세요, {client_name}님.</p>
        <p>{company_name}의 {sender.name or sender.email}입니다.</p>
        <p>{created_date}에 요청드린 {project.project_name} 시안에 대한 피드백을 기다리고 있습니다.<br>
        원활한 프로젝트 진행을 위해 확인 부탁드립니다.</p>

        <hr style="border: 1px solid #e5e7eb; margin: 20px 0;">
        <p><strong>📋 요청 정보</strong></p>
        <ul style="list-style: none; padding-left: 0;">
            <li>• 프로젝트: {project.project_name}</li>
            <li>• 최초 요청일: {created_date}</li>
            <li>• 경과일: {elapsed}일</li>
        </ul>

        <hr style="border: 1px solid #e5e7eb; margin: 20px 0;">

        <div style="text-align: center; margin: 30px 0;">
            <a href="{portal_url}" style="background-color: #3b82f6; color: white; padding: 12px 32px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                시안 확인하기 →
            </a>
        </div>

        <hr style="border: 1px solid #e5e7eb; margin: 20px 0;">
        <p style="color: #6b7280; font-size: 13px;">
            본 메일은 자동 발송되었습니다.<br>
            이미 피드백을 제출하셨다면 본 메일을 무시해주세요.
        </p>
    </div>
    """

    await send_email(
        to_emails=[fb_req.recipient_email],
        subject=f"[리마인드] {project.project_name} 시안 확인을 기다리고 있습니다",
        html_body=html_body,
    )


# ══════════════════════════════════════════
#  조회 헬퍼
# ══════════════════════════════════════════

async def list_feedback_requests(
    db: AsyncSession,
    user_id: int,
    project_id: int | None = None,
) -> list[dict]:
    """PM의 피드백 요청 목록 조회"""
    q = select(FeedbackRequest, Project.project_name).join(
        Project, Project.id == FeedbackRequest.project_id
    ).where(FeedbackRequest.sender_id == user_id)

    if project_id:
        q = q.where(FeedbackRequest.project_id == project_id)

    q = q.order_by(FeedbackRequest.created_at.desc()).limit(50)
    result = await db.execute(q)

    return [{
        "id": fr.id,
        "project_id": fr.project_id,
        "project_name": pname,
        "recipient_email": fr.recipient_email,
        "subject": fr.subject,
        "status": fr.status,
        "reminder_count": fr.reminder_count,
        "feedback_deadline": fr.feedback_deadline,
        "viewed_at": fr.viewed_at.isoformat() if fr.viewed_at else None,
        "responded_at": fr.responded_at.isoformat() if fr.responded_at else None,
        "created_at": fr.created_at.isoformat() if fr.created_at else None,
    } for fr, pname in result.all()]


async def get_feedback_request_detail(
    db: AsyncSession,
    request_id: int,
    user_id: int,
) -> dict | None:
    """피드백 요청 상세 조회 (응답 포함)"""
    fb_req = await db.get(FeedbackRequest, request_id)
    if not fb_req or fb_req.sender_id != user_id:
        return None

    project = await db.get(Project, fb_req.project_id)

    # 응답 조회
    resp_result = await db.execute(
        select(FeedbackResponse).where(
            FeedbackResponse.feedback_request_id == fb_req.id
        ).order_by(FeedbackResponse.created_at.asc())
    )
    responses = resp_result.scalars().all()

    return {
        "id": fb_req.id,
        "project_name": project.project_name if project else None,
        "recipient_email": fb_req.recipient_email,
        "subject": fb_req.subject,
        "message": fb_req.message,
        "figma_url": fb_req.figma_url,
        "status": fb_req.status,
        "reminder_count": fb_req.reminder_count,
        "feedback_deadline": fb_req.feedback_deadline,
        "viewed_at": fb_req.viewed_at.isoformat() if fb_req.viewed_at else None,
        "responded_at": fb_req.responded_at.isoformat() if fb_req.responded_at else None,
        "created_at": fb_req.created_at.isoformat() if fb_req.created_at else None,
        "responses": [{
            "id": r.id,
            "response_type": r.response_type,
            "content": r.content,
            "client_name": r.client_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in responses],
    }


async def cancel_feedback_request(
    db: AsyncSession,
    request_id: int,
    user_id: int,
) -> bool:
    """피드백 요청 취소 (리마인더 중단)"""
    fb_req = await db.get(FeedbackRequest, request_id)
    if not fb_req or fb_req.sender_id != user_id:
        return False
    if fb_req.status == "responded":
        return False

    fb_req.status = "cancelled"
    await db.commit()
    return True
