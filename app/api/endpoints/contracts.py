from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, or_
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime
from pathlib import Path
import uuid
import shutil
import json as json_mod
import re as re_mod
import logging

from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db, Contract, User, Team, TeamMember, ActivityLog, Notification, utc_now
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter

logger = logging.getLogger(__name__)

# 증빙 파일 저장 경로
EVIDENCE_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()


async def _user_team_ids(db: AsyncSession, user_id: int) -> list[int]:
    """사용자가 속한 모든 팀 ID 목록"""
    result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user_id)
    )
    return [row[0] for row in result.all()]


def _accessible_filter(user_id: int, team_ids: list[int]):
    """개인 계약 + 팀 계약 접근 필터 생성"""
    conditions = [
        # 개인 계약 (team_id가 없는 본인 소유)
        (Contract.user_id == user_id) & (Contract.team_id == None)  # noqa: E711
    ]
    if team_ids:
        # 팀 계약
        conditions.append(Contract.team_id.in_(team_ids))
    return or_(*conditions)


async def _get_accessible_contract(
    db: AsyncSession, contract_id: int, user_id: int, team_ids: list[int]
) -> Optional[Contract]:
    """접근 가능한 계약 1건 조회"""
    result = await db.execute(
        select(Contract).where(
            Contract.id == contract_id,
            _accessible_filter(user_id, team_ids),
        )
    )
    return result.scalar_one_or_none()


class ScheduleItem(BaseModel):
    phase: str
    schedule_type: str
    start_date: str
    end_date: str
    description: str
    deliverables: List[str] = []


class TaskItem(BaseModel):
    task_name: str
    priority: str
    deadline: str
    description: str


class ContractCreate(BaseModel):
    contract_name: str = Field(..., min_length=1, max_length=500)
    team_id: Optional[int] = None
    file_name: Optional[str] = Field(None, max_length=500)
    company_name: Optional[str] = Field(None, max_length=300)
    contractor: Optional[str] = Field(None, max_length=300)
    client: Optional[str] = Field(None, max_length=300)
    contract_date: Optional[str] = Field(None, max_length=50)
    contract_start_date: Optional[str] = Field(None, max_length=50)
    contract_end_date: Optional[str] = Field(None, max_length=50)
    total_duration_days: Optional[int] = Field(None, ge=0, le=36500)
    contract_amount: Optional[str] = Field(None, max_length=200)
    payment_method: Optional[str] = Field(None, max_length=500)
    payment_due_date: Optional[str] = Field(None, max_length=50)
    schedules: Optional[List[dict]] = None
    tasks: Optional[List[dict]] = None
    milestones: Optional[List[str]] = None
    raw_text: Optional[str] = None


class ContractResponse(BaseModel):
    id: int
    contract_name: str
    team_id: Optional[int] = None
    file_name: Optional[str]
    company_name: Optional[str]
    contractor: Optional[str]
    client: Optional[str]
    contract_date: Optional[str]
    contract_start_date: Optional[str]
    contract_end_date: Optional[str]
    total_duration_days: Optional[int]
    contract_amount: Optional[str]
    payment_method: Optional[str]
    payment_due_date: Optional[str]
    schedules: Optional[List[dict]]
    tasks: Optional[List[dict]]
    milestones: Optional[List[str]]
    raw_text: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.post("/save", response_model=ContractResponse)
@limiter.limit("30/minute")
async def save_contract(
    contract_data: ContractCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """계약 정보 저장"""
    try:
        user = await require_current_user(request, db)
        team_ids = await _user_team_ids(db, user.id)

        # 팀 계약인 경우 멤버 확인
        if contract_data.team_id:
            if contract_data.team_id not in team_ids:
                raise HTTPException(status_code=403, detail="해당 팀의 멤버가 아닙니다.")

        # 동일한 계약명이 있는지 확인 (접근 가능 범위 내)
        dup_query = select(Contract).where(
            Contract.contract_name == contract_data.contract_name,
            _accessible_filter(user.id, team_ids),
        )
        result = await db.execute(dup_query)
        existing_contract = result.scalar_one_or_none()

        if existing_contract:
            raise HTTPException(
                status_code=409,
                detail="동일한 이름의 계약서가 이미 존재합니다."
            )

        # 새 계약 생성
        contract = Contract(
            user_id=user.id,
            team_id=contract_data.team_id,
            contract_name=contract_data.contract_name,
            file_name=contract_data.file_name,
            company_name=contract_data.company_name,
            contractor=contract_data.contractor,
            client=contract_data.client,
            contract_date=contract_data.contract_date,
            contract_start_date=contract_data.contract_start_date,
            contract_end_date=contract_data.contract_end_date,
            total_duration_days=contract_data.total_duration_days,
            contract_amount=contract_data.contract_amount,
            payment_method=contract_data.payment_method,
            payment_due_date=contract_data.payment_due_date,
            schedules=contract_data.schedules,
            tasks=contract_data.tasks,
            milestones=contract_data.milestones,
            raw_text=contract_data.raw_text
        )
        db.add(contract)
        await db.flush()

        # 활동 로그
        await _log_activity(db, user.id, contract, "create", "contract", contract.contract_name)

        await db.commit()
        await db.refresh(contract)

        return contract
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"계약 저장 실패: {e}")
        raise HTTPException(status_code=500, detail="계약 저장 중 오류가 발생했습니다.")


@router.get("/list")
async def list_contracts(
    request: Request,
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    team_id: Optional[int] = Query(None, description="팀 ID 필터"),
    db: AsyncSession = Depends(get_db)
):
    """사용자의 계약 목록 조회 (페이지네이션)"""
    user = await require_current_user(request, db)
    user_team_ids = await _user_team_ids(db, user.id)

    # 접근 필터
    if team_id is not None:
        if team_id not in user_team_ids:
            raise HTTPException(status_code=403, detail="해당 팀의 멤버가 아닙니다.")
        access = Contract.team_id == team_id
    else:
        access = _accessible_filter(user.id, user_team_ids)

    # 전체 개수
    count_result = await db.execute(
        select(func.count()).select_from(Contract).where(access)
    )
    total = count_result.scalar()

    # 페이지네이션 적용
    result = await db.execute(
        select(Contract)
        .where(access)
        .order_by(desc(Contract.created_at))
        .offset((page - 1) * size)
        .limit(size)
    )
    contracts = result.scalars().all()

    return {
        "items": [ContractResponse.model_validate(c) for c in contracts],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    request: Request,
    team_id: Optional[int] = Query(None, description="팀 ID 필터"),
    db: AsyncSession = Depends(get_db)
):
    """대시보드 요약 정보 조회"""
    user = await require_current_user(request, db)
    user_team_ids = await _user_team_ids(db, user.id)

    if team_id is not None:
        if team_id not in user_team_ids:
            raise HTTPException(status_code=403, detail="해당 팀의 멤버가 아닙니다.")
        access = Contract.team_id == team_id
    else:
        access = _accessible_filter(user.id, user_team_ids)

    result = await db.execute(
        select(Contract)
        .where(access)
        .order_by(desc(Contract.created_at))
        .limit(200)
    )
    contracts = result.scalars().all()

    # 모든 업무 수집
    all_tasks = []
    for contract in contracts:
        if contract.tasks:
            for task in contract.tasks:
                all_tasks.append({
                    **task,
                    "contract_id": contract.id,
                    "contract_name": contract.contract_name
                })

    # 날짜순 정렬 (due_date 기준, 날짜 없는 항목은 맨 뒤로)
    def sort_by_date(task):
        due_date = task.get("due_date", "")
        if not due_date:
            return "9999-99-99"  # 날짜 없으면 맨 뒤로
        return due_date

    all_tasks.sort(key=sort_by_date)

    # 모든 일정 수집
    all_schedules = []
    for contract in contracts:
        if contract.schedules:
            for schedule in contract.schedules:
                all_schedules.append({
                    **schedule,
                    "contract_id": contract.id,
                    "contract_name": contract.contract_name
                })

    # 일정도 시작일 기준 정렬
    def sort_schedule_by_date(schedule):
        start_date = schedule.get("start_date", "")
        if not start_date:
            return "9999-99-99"
        return start_date

    all_schedules.sort(key=sort_schedule_by_date)

    # 통계 계산
    total_contracts = len(contracts)
    total_tasks = len(all_tasks)
    pending_tasks = len([t for t in all_tasks if t.get("status") == "대기"])
    in_progress_tasks = len([t for t in all_tasks if t.get("status") == "진행중"])
    completed_tasks = len([t for t in all_tasks if t.get("status") == "완료"])

    return {
        "total_contracts": total_contracts,
        "total_tasks": total_tasks,
        "pending_tasks": pending_tasks,
        "in_progress_tasks": in_progress_tasks,
        "completed_tasks": completed_tasks,
        "tasks": all_tasks,
        "schedules": all_schedules,
        "contracts": [
            {
                "id": c.id,
                "contract_name": c.contract_name,
                "contract_start_date": c.contract_start_date,
                "contract_end_date": c.contract_end_date,
                "task_count": len(c.tasks) if c.tasks else 0,
                "schedule_count": len(c.schedules) if c.schedules else 0
            }
            for c in contracts
        ]
    }


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """특정 계약 상세 조회"""
    user = await require_current_user(request, db)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    return contract


class ContractUpdate(BaseModel):
    contract_name: Optional[str] = Field(None, min_length=1, max_length=500)
    company_name: Optional[str] = Field(None, max_length=300)
    contractor: Optional[str] = Field(None, max_length=300)
    client: Optional[str] = Field(None, max_length=300)
    contract_date: Optional[str] = Field(None, max_length=50)
    contract_start_date: Optional[str] = Field(None, max_length=50)
    contract_end_date: Optional[str] = Field(None, max_length=50)
    total_duration_days: Optional[int] = Field(None, ge=0, le=36500)
    contract_amount: Optional[str] = Field(None, max_length=200)
    payment_method: Optional[str] = Field(None, max_length=500)
    payment_due_date: Optional[str] = Field(None, max_length=50)


@router.put("/{contract_id}", response_model=ContractResponse)
@limiter.limit("30/minute")
async def update_contract(
    contract_id: int,
    update_data: ContractUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """계약 정보 수정"""
    try:
        user = await require_current_user(request, db)
        team_ids = await _user_team_ids(db, user.id)

        contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
        if not contract:
            raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

        # 계약명 중복 확인 (변경 시)
        if update_data.contract_name and update_data.contract_name != contract.contract_name:
            dup_result = await db.execute(
                select(Contract).where(
                    _accessible_filter(user.id, team_ids),
                    Contract.contract_name == update_data.contract_name,
                    Contract.id != contract_id,
                )
            )
            if dup_result.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="동일한 이름의 계약서가 이미 존재합니다.")

        # 전달된 필드만 업데이트
        update_fields = update_data.model_dump(exclude_unset=True)
        changed = ", ".join(update_fields.keys())
        for field, value in update_fields.items():
            setattr(contract, field, value)

        await _log_activity(db, user.id, contract, "update", "contract", contract.contract_name, f"변경: {changed}")

        await db.commit()
        await db.refresh(contract)

        return contract
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"계약 수정 실패: {e}")
        raise HTTPException(status_code=500, detail="계약 수정 중 오류가 발생했습니다.")


class TaskCreate(BaseModel):
    task_name: str = Field(..., min_length=1, max_length=300)
    phase: Optional[str] = Field("", max_length=200)
    due_date: Optional[str] = Field("", max_length=50)
    priority: Optional[str] = Field("보통", max_length=20)
    status: Optional[str] = Field("대기", max_length=20)
    assignee_id: Optional[int] = None


class StandaloneTaskCreate(BaseModel):
    contract_id: Optional[int] = None
    task_name: str = Field(..., min_length=1, max_length=300)
    phase: Optional[str] = Field("", max_length=200)
    due_date: Optional[str] = Field("", max_length=50)
    priority: Optional[str] = Field("보통", max_length=20)
    status: Optional[str] = Field("대기", max_length=20)
    assignee_id: Optional[int] = None


class TaskStatusUpdate(BaseModel):
    task_id: str = Field(..., max_length=20)
    status: str = Field(..., max_length=20)


class TaskNoteUpdate(BaseModel):
    task_id: str = Field(..., max_length=20)
    note: str = Field(..., max_length=5000)


class TaskAssigneeUpdate(BaseModel):
    task_id: str = Field(..., max_length=20)
    assignee_id: Optional[int] = None  # null이면 담당자 해제


def _validate_task_id(task_id: str) -> str:
    """task_id 형식 검증 (경로 탐색 방지)"""
    if not re_mod.match(r'^TASK-\d{1,6}$', str(task_id)):
        raise HTTPException(status_code=400, detail="잘못된 업무 ID 형식입니다.")
    return str(task_id)


async def _log_activity(
    db: AsyncSession, user_id: int, contract: Contract,
    action: str, target_type: str, target_name: str, detail: str = None,
):
    """활동 로그 기록"""
    try:
        db.add(ActivityLog(
            contract_id=contract.id,
            team_id=contract.team_id,
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_name=target_name,
            detail=detail,
        ))
    except Exception as e:
        logger.warning(f"활동 로그 기록 실패: {e}")


async def _notify_team_members(
    db: AsyncSession, contract: Contract, sender_id: int,
    ntype: str, title: str, message: str = None,
):
    """팀 계약의 멤버에게 알림 (발신자 제외)"""
    if not contract.team_id:
        return
    result = await db.execute(
        select(TeamMember.user_id).where(
            TeamMember.team_id == contract.team_id,
            TeamMember.user_id != sender_id,
        )
    )
    for (uid,) in result.all():
        db.add(Notification(
            user_id=uid,
            type=ntype,
            title=title,
            message=message,
            link=json_mod.dumps({"contract_id": contract.id}),
        ))


async def _resolve_assignee(db: AsyncSession, assignee_id: Optional[int], contract: Contract) -> dict:
    """담당자 ID로 이름 조회. 팀 계약이면 팀 멤버인지 검증."""
    if not assignee_id:
        return {"assignee_id": None, "assignee_name": None}

    # 팀 계약이면 팀 멤버인지 확인
    if contract.team_id:
        result = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == contract.team_id,
                TeamMember.user_id == assignee_id,
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="팀 멤버만 담당자로 지정할 수 있습니다.")

    result = await db.execute(select(User).where(User.id == assignee_id))
    assignee = result.scalar_one_or_none()
    if not assignee:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다.")

    return {"assignee_id": assignee.id, "assignee_name": assignee.name or assignee.email}


@router.post("/tasks/add")
async def add_standalone_task(
    task_data: StandaloneTaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """업무 추가 (계약 선택 또는 미분류)"""
    user = await require_current_user(request, db)
    team_ids = await _user_team_ids(db, user.id)

    if task_data.contract_id:
        contract = await _get_accessible_contract(db, task_data.contract_id, user.id, team_ids)
        if not contract:
            raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")
    else:
        # 미분류 계약 조회 또는 생성
        result = await db.execute(
            select(Contract)
            .where(Contract.user_id == user.id, Contract.contract_name == "미분류", Contract.team_id == None)  # noqa: E711
        )
        contract = result.scalar_one_or_none()

        if not contract:
            contract = Contract(
                user_id=user.id,
                contract_name="미분류",
                tasks=[],
            )
            db.add(contract)
            await db.flush()

    if not contract.tasks:
        contract.tasks = []

    # 담당자 확인
    assignee_info = await _resolve_assignee(db, task_data.assignee_id, contract)

    # task_id 자동 생성
    existing_ids = [t.get("task_id", 0) for t in contract.tasks]
    max_id = max([int(str(tid).replace("TASK-", "")) for tid in existing_ids if str(tid).replace("TASK-", "").isdigit()] or [0])
    new_task_id = f"TASK-{max_id + 1:03d}"

    new_task = {
        "task_id": new_task_id,
        "task_name": task_data.task_name,
        "phase": task_data.phase,
        "due_date": task_data.due_date,
        "priority": task_data.priority,
        "status": task_data.status,
        **assignee_info,
    }

    contract.tasks.append(new_task)
    flag_modified(contract, "tasks")

    await _log_activity(db, user.id, contract, "create", "task", task_data.task_name)

    await db.commit()

    return {"message": "업무가 추가되었습니다", "task": {**new_task, "contract_id": contract.id, "contract_name": contract.contract_name}}


@router.post("/{contract_id}/tasks")
async def add_task(
    contract_id: int,
    task_data: TaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """계약에 업무 추가"""
    user = await require_current_user(request, db)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    if not contract.tasks:
        contract.tasks = []

    # 담당자 확인
    assignee_info = await _resolve_assignee(db, task_data.assignee_id, contract)

    # task_id 자동 생성
    existing_ids = [t.get("task_id", 0) for t in contract.tasks]
    max_id = max([int(str(tid).replace("TASK-", "")) for tid in existing_ids if str(tid).replace("TASK-", "").isdigit()] or [0])
    new_task_id = f"TASK-{max_id + 1:03d}"

    new_task = {
        "task_id": new_task_id,
        "task_name": task_data.task_name,
        "phase": task_data.phase,
        "due_date": task_data.due_date,
        "priority": task_data.priority,
        "status": task_data.status,
        **assignee_info,
    }

    contract.tasks.append(new_task)
    flag_modified(contract, "tasks")

    await _log_activity(db, user.id, contract, "create", "task", task_data.task_name)

    await db.commit()

    return {"message": "업무가 추가되었습니다", "task": {**new_task, "contract_id": contract_id, "contract_name": contract.contract_name}}


@router.patch("/{contract_id}/tasks/status")
async def update_task_status(
    contract_id: int,
    update: TaskStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """업무 상태 변경"""
    user = await require_current_user(request, db)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    if not contract.tasks:
        raise HTTPException(status_code=404, detail="업무 목록이 없습니다")

    updated = False
    task_name = ""
    old_status = ""
    for task in contract.tasks:
        if str(task.get("task_id")) == str(update.task_id):
            old_status = task.get("status", "")
            task_name = task.get("task_name", "")
            task["status"] = update.status
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail="해당 업무를 찾을 수 없습니다")

    flag_modified(contract, "tasks")

    await _log_activity(db, user.id, contract, "status_change", "task", task_name, f"{old_status} -> {update.status}")
    await _notify_team_members(db, contract, user.id, "status_change",
        f"{user.name or user.email}님이 '{task_name}' 상태를 변경했습니다",
        f"{old_status} -> {update.status}")

    await db.commit()

    return {"message": "상태가 변경되었습니다", "task_id": update.task_id, "status": update.status}


@router.patch("/{contract_id}/tasks/note")
async def update_task_note(
    contract_id: int,
    update: TaskNoteUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """업무 처리 내용 저장"""
    user = await require_current_user(request, db)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract or not contract.tasks:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    updated = False
    for task in contract.tasks:
        if str(task.get("task_id")) == str(update.task_id):
            task["note"] = update.note
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail="해당 업무를 찾을 수 없습니다")

    flag_modified(contract, "tasks")
    await db.commit()

    return {"message": "처리 내용이 저장되었습니다"}


@router.delete("/{contract_id}/tasks/{task_id}")
async def delete_task(
    contract_id: int,
    task_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """개별 업무 삭제"""
    user = await require_current_user(request, db)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract or not contract.tasks:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    original_len = len(contract.tasks)
    deleted_name = ""
    for t in contract.tasks:
        if str(t.get("task_id")) == str(task_id):
            deleted_name = t.get("task_name", "")
            break
    contract.tasks = [t for t in contract.tasks if str(t.get("task_id")) != str(task_id)]

    if len(contract.tasks) == original_len:
        raise HTTPException(status_code=404, detail="해당 업무를 찾을 수 없습니다")

    await _log_activity(db, user.id, contract, "delete", "task", deleted_name)

    # 해당 업무의 증빙 파일도 삭제
    task_evidence_dir = EVIDENCE_DIR / str(contract_id) / str(task_id)
    if task_evidence_dir.exists():
        shutil.rmtree(task_evidence_dir, ignore_errors=True)

    flag_modified(contract, "tasks")
    await db.commit()

    return {"message": "업무가 삭제되었습니다", "task_id": task_id}


@router.post("/{contract_id}/tasks/attachment")
@limiter.limit("20/minute")
async def upload_task_attachment(
    contract_id: int,
    task_id: str = Form(...),
    file: UploadFile = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """업무 증빙 파일 업로드"""
    user = await require_current_user(request, db)
    _validate_task_id(task_id)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract or not contract.tasks:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    # H-6: 파일 크기를 스트리밍으로 체크 (메모리 고갈 방지)
    max_size = 20 * 1024 * 1024
    chunks = []
    total_size = 0
    while chunk := await file.read(8192):
        total_size += len(chunk)
        if total_size > max_size:
            raise HTTPException(status_code=400, detail="파일 크기는 20MB를 초과할 수 없습니다")
        chunks.append(chunk)
    contents = b"".join(chunks)

    # 파일 저장
    ext = Path(file.filename).suffix
    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_dir = EVIDENCE_DIR / str(contract_id) / str(task_id)
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / saved_name

    with open(save_path, "wb") as f:
        f.write(contents)

    # 업무에 첨부파일 정보 추가
    attachment = {
        "filename": saved_name,
        "original_name": file.filename,
        "uploaded_at": utc_now().strftime("%Y-%m-%d %H:%M"),
    }

    updated = False
    for task in contract.tasks:
        if str(task.get("task_id")) == str(task_id):
            if "attachments" not in task:
                task["attachments"] = []
            task["attachments"].append(attachment)
            updated = True
            break

    if not updated:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="해당 업무를 찾을 수 없습니다")

    flag_modified(contract, "tasks")
    await db.commit()

    return {"message": "파일이 업로드되었습니다", "attachment": attachment}


@router.delete("/{contract_id}/tasks/attachment")
@limiter.limit("20/minute")
async def delete_task_attachment(
    contract_id: int,
    task_id: str,
    filename: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """업무 증빙 파일 삭제"""
    user = await require_current_user(request, db)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract or not contract.tasks:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    found = False
    for task in contract.tasks:
        if str(task.get("task_id")) == str(task_id):
            attachments = task.get("attachments", [])
            task["attachments"] = [a for a in attachments if a["filename"] != filename]
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="해당 업무를 찾을 수 없습니다")

    # 파일 삭제
    file_path = EVIDENCE_DIR / str(contract_id) / str(task_id) / filename
    file_path.unlink(missing_ok=True)

    flag_modified(contract, "tasks")
    await db.commit()

    return {"message": "파일이 삭제되었습니다"}


@router.get("/attachment/{contract_id}/{task_id}/{filename}")
async def get_attachment(
    contract_id: int,
    task_id: str,
    filename: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """증빙 파일 다운로드"""
    user = await require_current_user(request, db)
    _validate_task_id(task_id)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    # 경로 탐색 공격 방지 (문자열 검사 + resolve 검증)
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다")

    file_path = (EVIDENCE_DIR / str(contract_id) / str(task_id) / filename).resolve()
    if not str(file_path).startswith(str(EVIDENCE_DIR.resolve())):
        raise HTTPException(status_code=400, detail="잘못된 파일 경로입니다")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    # 원본 파일명 조회
    original_name = filename
    if contract.tasks:
        for task in contract.tasks:
            if str(task.get("task_id")) == str(task_id):
                for att in task.get("attachments", []):
                    if att.get("filename") == filename:
                        original_name = att.get("original_name", filename)
                        break
                break

    return FileResponse(file_path, filename=original_name)


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """계약 삭제"""
    user = await require_current_user(request, db)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    # 활동 로그 (삭제 전에 기록)
    await _log_activity(db, user.id, contract, "delete", "contract", contract.contract_name)

    # 증빙 파일 디렉토리 삭제
    evidence_dir = EVIDENCE_DIR / str(contract_id)
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir, ignore_errors=True)

    await db.delete(contract)
    await db.commit()

    return {"message": "계약이 삭제되었습니다"}


# ============ 담당자 지정 ============

@router.patch("/{contract_id}/tasks/assignee")
async def update_task_assignee(
    contract_id: int,
    update: TaskAssigneeUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """업무 담당자 지정/변경"""
    user = await require_current_user(request, db)
    team_ids = await _user_team_ids(db, user.id)

    contract = await _get_accessible_contract(db, contract_id, user.id, team_ids)
    if not contract or not contract.tasks:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    assignee_info = await _resolve_assignee(db, update.assignee_id, contract)

    updated = False
    task_name = ""
    for task in contract.tasks:
        if str(task.get("task_id")) == str(update.task_id):
            task_name = task.get("task_name", "")
            task["assignee_id"] = assignee_info["assignee_id"]
            task["assignee_name"] = assignee_info["assignee_name"]
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail="해당 업무를 찾을 수 없습니다")

    flag_modified(contract, "tasks")

    await _log_activity(db, user.id, contract, "assign", "task", task_name,
        f"담당자: {assignee_info['assignee_name'] or '없음'}")

    # 담당자에게 알림
    if update.assignee_id and update.assignee_id != user.id:
        db.add(Notification(
            user_id=update.assignee_id,
            type="assign",
            title=f"{user.name or user.email}님이 '{task_name}' 업무를 배정했습니다",
            message=f"계약: {contract.contract_name}",
            link=json_mod.dumps({"contract_id": contract.id, "task_id": update.task_id}),
        ))

    await db.commit()

    return {"message": "담당자가 변경되었습니다", "task_id": update.task_id, **assignee_info}
