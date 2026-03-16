"""AI 업무 보고 + 자동 퇴근 API — 6차 개발 Phase 3-3

GET  /work-report/today     — 오늘의 AI 활동 요약
POST /work-report/submit    — 업무 보고 제출 + 자동 퇴근
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone

from app.database import get_db, Attendance, TeamMember, AttendancePolicy, User
from app.api.endpoints.auth import require_current_user
from app.services.work_report_service import generate_daily_work_summary

logger = logging.getLogger(__name__)
router = APIRouter()

KST = timezone(timedelta(hours=9))


class WorkReportSubmit(BaseModel):
    memo: Optional[str] = Field(None, max_length=2000, description="추가 메모 (선택)")
    auto_checkout: bool = Field(True, description="퇴근 자동 기록 여부")


@router.get("/work-report/today")
async def get_today_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """오늘의 AI 업무 보고 데이터 (활동 요약)"""
    return await generate_daily_work_summary(db, current_user.id)


@router.post("/work-report/submit")
async def submit_work_report(
    body: WorkReportSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """업무 보고 제출 + 자동 퇴근"""
    now_kst = datetime.now(KST)
    today = now_kst.strftime("%Y-%m-%d")
    now_time = now_kst.strftime("%H:%M")

    # 활동 요약 생성
    report = await generate_daily_work_summary(db, current_user.id)

    result = {"report": report, "checkout": None}

    # 자동 퇴근 처리
    if body.auto_checkout:
        # 사용자의 팀 ID 가져오기
        team_result = await db.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == current_user.id).limit(1)
        )
        team_row = team_result.first()
        if not team_row:
            raise HTTPException(status_code=400, detail="소속 팀이 없습니다.")
        team_id = team_row[0]

        # 오늘 출퇴근 기록 확인
        att_result = await db.execute(
            select(Attendance).where(
                Attendance.team_id == team_id,
                Attendance.user_id == current_user.id,
                Attendance.date == today,
            )
        )
        record = att_result.scalar_one_or_none()

        if record and record.check_in and not record.check_out:
            # 퇴근 기록
            policy_result = await db.execute(
                select(AttendancePolicy).where(AttendancePolicy.team_id == team_id)
            )
            policy = policy_result.scalar_one_or_none()
            break_hours = policy.break_hours if policy else 1
            policy_in = policy.default_check_in if policy else "09:00"
            policy_out = policy.default_check_out if policy else "18:00"

            record.check_out = now_time

            # 근무시간 계산
            h1, m1 = map(int, record.check_in.split(":"))
            h2, m2 = map(int, now_time.split(":"))
            total_minutes = (h2 * 60 + m2) - (h1 * 60 + m1) - (break_hours * 60)
            if total_minutes < 0:
                total_minutes = 0
            record.work_hours = f"{total_minutes / 60:.2f}"

            # 상태 판별
            if record.check_in > policy_in:
                record.status = "late"
            elif now_time < policy_out:
                record.status = "early_leave"
            else:
                record.status = "normal"

            # 메모 추가
            if body.memo:
                record.note = body.memo

            result["checkout"] = {
                "check_out": now_time,
                "work_hours": record.work_hours,
                "status": record.status,
            }
        elif record and record.check_out:
            result["checkout"] = {"message": "이미 퇴근 처리되었습니다."}
        else:
            result["checkout"] = {"message": "출근 기록이 없어 퇴근을 기록할 수 없습니다."}

    await db.commit()
    return result
