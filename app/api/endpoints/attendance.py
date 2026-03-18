"""4차 개발 Phase 4 — 출퇴근 기록 / 근태 관리 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone, timedelta
import logging

from app.database import (
    get_db, Attendance, AttendancePolicy,
    TeamMember, User, utc_now,
)
from app.api.endpoints.auth import require_current_user
from app.api.endpoints.teams import get_team_member
from app.limiter import limiter
from fastapi import Request

logger = logging.getLogger(__name__)
router = APIRouter()

KST = timezone(timedelta(hours=9))


def _kst_now() -> datetime:
    return datetime.now(KST)


def _today_kst() -> str:
    return _kst_now().strftime("%Y-%m-%d")


def _time_kst() -> str:
    return _kst_now().strftime("%H:%M")


# ── Pydantic 모델 ──────────────────────────────

class AttendanceUpdate(BaseModel):
    check_in: Optional[str] = Field(None, pattern=r'^\d{2}:\d{2}$')
    check_out: Optional[str] = Field(None, pattern=r'^\d{2}:\d{2}$')
    note: Optional[str] = Field(None, max_length=500)


class PolicyUpdate(BaseModel):
    default_check_in: str = Field("09:00", pattern=r'^\d{2}:\d{2}$')
    default_check_out: str = Field("18:00", pattern=r'^\d{2}:\d{2}$')
    work_hours: int = Field(8, ge=1, le=24)
    break_hours: int = Field(1, ge=0, le=4)


# ── 헬퍼 ──────────────────────────────────────

def _calc_work_hours(check_in: str, check_out: str, break_hours: int = 1) -> str:
    """근무 시간 계산 (소수점)"""
    try:
        h1, m1 = map(int, check_in.split(":"))
        h2, m2 = map(int, check_out.split(":"))
        total_minutes = (h2 * 60 + m2) - (h1 * 60 + m1) - (break_hours * 60)
        if total_minutes < 0:
            total_minutes = 0
        hours = total_minutes / 60
        return f"{hours:.2f}"
    except Exception:
        return "0.00"


def _determine_status(check_in: str, check_out: str, policy_in: str, policy_out: str) -> str:
    """출근 상태 판별"""
    if not check_in:
        return "absent"
    if check_in > policy_in:
        return "late"
    if check_out and check_out < policy_out:
        return "early_leave"
    return "normal"


def _attendance_to_dict(a: Attendance, user_name: str = None) -> dict:
    return {
        "id": a.id,
        "team_id": a.team_id,
        "user_id": a.user_id,
        "user_name": user_name,
        "date": a.date,
        "check_in": a.check_in,
        "check_out": a.check_out,
        "work_hours": a.work_hours,
        "status": a.status,
        "note": a.note,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


async def _get_policy(db: AsyncSession, team_id: int) -> AttendancePolicy:
    result = await db.execute(
        select(AttendancePolicy).where(AttendancePolicy.team_id == team_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        policy = AttendancePolicy(team_id=team_id)
        db.add(policy)
        await db.commit()
        await db.refresh(policy)
    return policy


async def _get_user_team_id(db: AsyncSession, user_id: int) -> int:
    """사용자의 첫 번째 팀 ID"""
    result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user_id).limit(1)
    )
    team_id = result.scalar_one_or_none()
    if not team_id:
        raise HTTPException(status_code=400, detail="소속 팀이 없습니다.")
    return team_id


# ── 출퇴근 API ─────────────────────────────────

@router.post("/attendance/check-in")
@limiter.limit("10/minute")
async def check_in(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """출근 기록"""
    team_id = await _get_user_team_id(db, current_user.id)
    today = _today_kst()
    now_time = _time_kst()

    # 이미 출근했는지 확인
    existing = await db.execute(
        select(Attendance).where(
            Attendance.team_id == team_id,
            Attendance.user_id == current_user.id,
            Attendance.date == today,
        )
    )
    record = existing.scalar_one_or_none()
    if record and record.check_in:
        raise HTTPException(status_code=400, detail="이미 출근 처리되었습니다.")

    policy = await _get_policy(db, team_id)

    if record:
        record.check_in = now_time
        record.status = _determine_status(now_time, record.check_out, policy.default_check_in, policy.default_check_out)
    else:
        status = _determine_status(now_time, None, policy.default_check_in, policy.default_check_out)
        record = Attendance(
            team_id=team_id,
            user_id=current_user.id,
            date=today,
            check_in=now_time,
            status=status,
        )
        db.add(record)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="이미 출근 처리되었습니다. (동시 요청)")
    await db.refresh(record)
    return _attendance_to_dict(record, current_user.name)


@router.post("/attendance/check-out")
@limiter.limit("10/minute")
async def check_out(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """퇴근 기록"""
    team_id = await _get_user_team_id(db, current_user.id)
    today = _today_kst()
    now_time = _time_kst()

    existing = await db.execute(
        select(Attendance).where(
            Attendance.team_id == team_id,
            Attendance.user_id == current_user.id,
            Attendance.date == today,
        )
    )
    record = existing.scalar_one_or_none()
    if not record or not record.check_in:
        raise HTTPException(status_code=400, detail="출근 기록이 없습니다.")
    if record.check_out:
        raise HTTPException(status_code=400, detail="이미 퇴근 처리되었습니다.")

    policy = await _get_policy(db, team_id)

    record.check_out = now_time
    record.work_hours = _calc_work_hours(record.check_in, now_time, policy.break_hours)
    record.status = _determine_status(record.check_in, now_time, policy.default_check_in, policy.default_check_out)

    await db.commit()
    await db.refresh(record)
    return _attendance_to_dict(record, current_user.name)


@router.get("/attendance/today")
async def get_today(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """오늘 출퇴근 상태"""
    team_id = await _get_user_team_id(db, current_user.id)
    today = _today_kst()

    existing = await db.execute(
        select(Attendance).where(
            Attendance.team_id == team_id,
            Attendance.user_id == current_user.id,
            Attendance.date == today,
        )
    )
    record = existing.scalar_one_or_none()
    if not record:
        return {"date": today, "check_in": None, "check_out": None, "status": "미출근", "work_hours": None}

    return _attendance_to_dict(record, current_user.name)


@router.get("/attendance/my")
async def get_my_attendance(
    month: str = Query(..., pattern=r'^\d{4}-\d{2}$', description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """내 월별 근태 기록"""
    team_id = await _get_user_team_id(db, current_user.id)

    result = await db.execute(
        select(Attendance).where(
            Attendance.team_id == team_id,
            Attendance.user_id == current_user.id,
            Attendance.date >= f"{month}-01", Attendance.date <= f"{month}-31",
        ).order_by(Attendance.date)
    )
    records = result.scalars().all()

    # 통계
    total_days = len(records)
    total_hours = sum(float(r.work_hours or 0) for r in records)
    late_count = sum(1 for r in records if r.status == "late")
    early_leave_count = sum(1 for r in records if r.status == "early_leave")

    return {
        "month": month,
        "records": [_attendance_to_dict(r, current_user.name) for r in records],
        "stats": {
            "total_days": total_days,
            "total_hours": round(total_hours, 2),
            "late_count": late_count,
            "early_leave_count": early_leave_count,
            "avg_hours": round(total_hours / total_days, 2) if total_days else 0,
        },
    }


@router.get("/teams/{team_id}/attendance")
async def get_team_attendance(
    team_id: int,
    month: str = Query(..., pattern=r'^\d{4}-\d{2}$', description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """팀 근태 현황 (admin/owner)"""
    member = await get_team_member(db, team_id, current_user.id)
    if not member or member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="근태 현황 조회 권한이 없습니다.")

    # 팀 멤버 목록
    members_q = await db.execute(
        select(TeamMember, User)
        .join(User, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team_id)
    )
    members = members_q.all()

    result = []
    for tm, user in members:
        records_q = await db.execute(
            select(Attendance).where(
                Attendance.team_id == team_id,
                Attendance.user_id == user.id,
                Attendance.date >= f"{month}-01", Attendance.date <= f"{month}-31",
            ).order_by(Attendance.date)
        )
        records = records_q.scalars().all()

        total_hours = sum(float(r.work_hours or 0) for r in records)
        late_count = sum(1 for r in records if r.status == "late")

        result.append({
            "user_id": user.id,
            "user_name": user.name,
            "user_picture": user.picture,
            "role": tm.role,
            "total_days": len(records),
            "total_hours": round(total_hours, 2),
            "late_count": late_count,
            "records": [_attendance_to_dict(r, user.name) for r in records],
        })

    return {"team_id": team_id, "month": month, "members": result}


@router.put("/attendance/{attendance_id}")
async def update_attendance(
    attendance_id: int,
    body: AttendanceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """근태 수정 (본인 또는 admin)"""
    record = await db.get(Attendance, attendance_id)
    if not record:
        raise HTTPException(status_code=404, detail="근태 기록을 찾을 수 없습니다.")

    # 본인이거나 admin
    if record.user_id != current_user.id:
        member = await get_team_member(db, record.team_id, current_user.id)
        if not member or member.role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="수정 권한이 없습니다.")

    policy = await _get_policy(db, record.team_id)

    if body.check_in is not None:
        record.check_in = body.check_in
    if body.check_out is not None:
        record.check_out = body.check_out
    if body.note is not None:
        record.note = body.note

    # 근무시간 재계산
    if record.check_in and record.check_out:
        record.work_hours = _calc_work_hours(record.check_in, record.check_out, policy.break_hours)
        record.status = _determine_status(record.check_in, record.check_out, policy.default_check_in, policy.default_check_out)

    record.updated_at = utc_now()
    await db.commit()
    await db.refresh(record)

    user = await db.get(User, record.user_id)
    return _attendance_to_dict(record, user.name if user else None)


# ── 근무 정책 API ──────────────────────────────

@router.get("/teams/{team_id}/attendance/policy")
async def get_attendance_policy(
    team_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """근무 정책 조회"""
    member = await get_team_member(db, team_id, current_user.id)
    if not member:
        raise HTTPException(status_code=403, detail="팀 멤버가 아닙니다.")

    policy = await _get_policy(db, team_id)
    return {
        "team_id": team_id,
        "default_check_in": policy.default_check_in,
        "default_check_out": policy.default_check_out,
        "work_hours": policy.work_hours,
        "break_hours": policy.break_hours,
    }


@router.put("/teams/{team_id}/attendance/policy")
async def update_attendance_policy(
    team_id: int,
    body: PolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    """근무 정책 설정 (owner)"""
    member = await get_team_member(db, team_id, current_user.id)
    if not member or member.role != "owner":
        raise HTTPException(status_code=403, detail="근무 정책은 팀 소유자만 변경할 수 있습니다.")

    policy = await _get_policy(db, team_id)
    policy.default_check_in = body.default_check_in
    policy.default_check_out = body.default_check_out
    policy.work_hours = body.work_hours
    policy.break_hours = body.break_hours

    await db.commit()
    return {
        "ok": True,
        "team_id": team_id,
        "default_check_in": policy.default_check_in,
        "default_check_out": policy.default_check_out,
        "work_hours": policy.work_hours,
        "break_hours": policy.break_hours,
    }
