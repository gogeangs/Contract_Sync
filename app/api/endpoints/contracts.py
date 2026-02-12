from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from pathlib import Path
import uuid

from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db, Contract, User
from app.api.endpoints.auth import sessions

# 증빙 파일 저장 경로
EVIDENCE_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()


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
    contract_name: str
    file_name: Optional[str] = None
    company_name: Optional[str] = None
    contractor: Optional[str] = None
    client: Optional[str] = None
    contract_date: Optional[str] = None
    contract_start_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    total_duration_days: Optional[int] = None
    contract_amount: Optional[str] = None
    payment_method: Optional[str] = None
    payment_due_date: Optional[str] = None
    schedules: Optional[List[dict]] = None
    tasks: Optional[List[dict]] = None
    milestones: Optional[List[str]] = None
    raw_text: Optional[str] = None


class ContractResponse(BaseModel):
    id: int
    contract_name: str
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

    class Config:
        from_attributes = True


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """세션에서 현재 로그인된 사용자 가져오기"""
    session_token = request.cookies.get("session_token")
    if not session_token or session_token not in sessions:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    user_data = sessions[session_token]
    user_id = user_data.get("id")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")

    return user


@router.post("/save", response_model=ContractResponse)
async def save_contract(
    contract_data: ContractCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """계약 정보 저장"""
    try:
        user = await get_current_user(request, db)

        # 동일한 계약명이 있는지 확인
        result = await db.execute(
            select(Contract)
            .where(Contract.user_id == user.id, Contract.contract_name == contract_data.contract_name)
        )
        existing_contract = result.scalar_one_or_none()

        if existing_contract:
            raise HTTPException(
                status_code=409,
                detail="동일한 이름의 계약서가 이미 존재합니다."
            )

        # 새 계약 생성
        contract = Contract(
            user_id=user.id,
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

        await db.commit()
        await db.refresh(contract)

        return contract
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"저장 실패: {str(e)}")


@router.get("/list", response_model=List[ContractResponse])
async def list_contracts(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """사용자의 계약 목록 조회"""
    user = await get_current_user(request, db)

    result = await db.execute(
        select(Contract)
        .where(Contract.user_id == user.id)
        .order_by(desc(Contract.created_at))
    )
    contracts = result.scalars().all()

    return contracts


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """대시보드 요약 정보 조회"""
    user = await get_current_user(request, db)

    result = await db.execute(
        select(Contract)
        .where(Contract.user_id == user.id)
        .order_by(desc(Contract.created_at))
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
    user = await get_current_user(request, db)

    result = await db.execute(
        select(Contract)
        .where(Contract.id == contract_id, Contract.user_id == user.id)
    )
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    return contract


class TaskCreate(BaseModel):
    task_name: str
    phase: Optional[str] = ""
    due_date: Optional[str] = ""
    priority: Optional[str] = "보통"
    status: Optional[str] = "대기"


class StandaloneTaskCreate(BaseModel):
    contract_id: Optional[int] = None
    task_name: str
    phase: Optional[str] = ""
    due_date: Optional[str] = ""
    priority: Optional[str] = "보통"
    status: Optional[str] = "대기"


class TaskStatusUpdate(BaseModel):
    task_id: str
    status: str  # 대기, 진행중, 완료, 보류


class TaskNoteUpdate(BaseModel):
    task_id: str
    note: str


@router.post("/tasks/add")
async def add_standalone_task(
    task_data: StandaloneTaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """업무 추가 (계약 선택 또는 미분류)"""
    user = await get_current_user(request, db)

    if task_data.contract_id:
        # 기존 계약에 업무 추가
        result = await db.execute(
            select(Contract)
            .where(Contract.id == task_data.contract_id, Contract.user_id == user.id)
        )
        contract = result.scalar_one_or_none()
        if not contract:
            raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")
    else:
        # 미분류 계약 조회 또는 생성
        result = await db.execute(
            select(Contract)
            .where(Contract.user_id == user.id, Contract.contract_name == "미분류")
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

    # task_id 자동 생성
    existing_ids = [t.get("task_id", 0) for t in contract.tasks]
    max_id = max([int(str(tid).replace("TASK-", "")) for tid in existing_ids if str(tid).replace("TASK-", "").isdigit()] or [0])
    new_task_id = f"TASK-{str(max_id + 1).zfill(3)}"

    new_task = {
        "task_id": new_task_id,
        "task_name": task_data.task_name,
        "phase": task_data.phase,
        "due_date": task_data.due_date,
        "priority": task_data.priority,
        "status": task_data.status
    }

    contract.tasks.append(new_task)
    flag_modified(contract, "tasks")
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
    user = await get_current_user(request, db)

    result = await db.execute(
        select(Contract)
        .where(Contract.id == contract_id, Contract.user_id == user.id)
    )
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    if not contract.tasks:
        contract.tasks = []

    # task_id 자동 생성
    existing_ids = [t.get("task_id", 0) for t in contract.tasks]
    max_id = max([int(str(tid).replace("TASK-", "")) for tid in existing_ids if str(tid).replace("TASK-", "").isdigit()] or [0])
    new_task_id = f"TASK-{str(max_id + 1).zfill(3)}"

    new_task = {
        "task_id": new_task_id,
        "task_name": task_data.task_name,
        "phase": task_data.phase,
        "due_date": task_data.due_date,
        "priority": task_data.priority,
        "status": task_data.status
    }

    contract.tasks.append(new_task)
    flag_modified(contract, "tasks")
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
    user = await get_current_user(request, db)

    result = await db.execute(
        select(Contract)
        .where(Contract.id == contract_id, Contract.user_id == user.id)
    )
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    if not contract.tasks:
        raise HTTPException(status_code=404, detail="업무 목록이 없습니다")

    updated = False
    for task in contract.tasks:
        if str(task.get("task_id")) == str(update.task_id):
            task["status"] = update.status
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail="해당 업무를 찾을 수 없습니다")

    flag_modified(contract, "tasks")
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
    user = await get_current_user(request, db)

    result = await db.execute(
        select(Contract)
        .where(Contract.id == contract_id, Contract.user_id == user.id)
    )
    contract = result.scalar_one_or_none()

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


@router.post("/{contract_id}/tasks/attachment")
async def upload_task_attachment(
    contract_id: int,
    task_id: str = Form(...),
    file: UploadFile = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """업무 증빙 파일 업로드"""
    user = await get_current_user(request, db)

    result = await db.execute(
        select(Contract)
        .where(Contract.id == contract_id, Contract.user_id == user.id)
    )
    contract = result.scalar_one_or_none()

    if not contract or not contract.tasks:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")

    # 파일 크기 제한 (20MB)
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="파일 크기는 20MB를 초과할 수 없습니다")

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
        "uploaded_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
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
async def delete_task_attachment(
    contract_id: int,
    task_id: str,
    filename: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """업무 증빙 파일 삭제"""
    user = await get_current_user(request, db)

    result = await db.execute(
        select(Contract)
        .where(Contract.id == contract_id, Contract.user_id == user.id)
    )
    contract = result.scalar_one_or_none()

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
    user = await get_current_user(request, db)

    # 해당 계약이 사용자 소유인지 확인
    result = await db.execute(
        select(Contract)
        .where(Contract.id == contract_id, Contract.user_id == user.id)
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    file_path = EVIDENCE_DIR / str(contract_id) / str(task_id) / filename
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
    user = await get_current_user(request, db)

    result = await db.execute(
        select(Contract)
        .where(Contract.id == contract_id, Contract.user_id == user.id)
    )
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    await db.delete(contract)
    await db.commit()

    return {"message": "계약이 삭제되었습니다"}
