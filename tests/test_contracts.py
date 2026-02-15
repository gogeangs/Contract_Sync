import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_create_contract(auth_client):
    """계약 생성"""
    resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "테스트 계약서",
        "company_name": "테스트 기업",
        "contractor": "수급자",
        "client": "발주처",
        "contract_start_date": "2025-01-01",
        "contract_end_date": "2025-12-31",
        "tasks": [
            {"task_id": "TASK-001", "task_name": "업무1", "phase": "1단계", "due_date": "2025-03-01", "priority": "높음", "status": "대기"}
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["contract_name"] == "테스트 계약서"
    assert data["id"] is not None
    assert len(data["tasks"]) == 1


@pytest.mark.asyncio
async def test_create_duplicate_contract(auth_client):
    """중복 계약명 생성 거부"""
    await auth_client.post("/api/v1/contracts/save", json={"contract_name": "중복 테스트"})
    resp = await auth_client.post("/api/v1/contracts/save", json={"contract_name": "중복 테스트"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_contracts(auth_client):
    """계약 목록 조회"""
    # 2개 계약 생성
    await auth_client.post("/api/v1/contracts/save", json={"contract_name": "계약A"})
    await auth_client.post("/api/v1/contracts/save", json={"contract_name": "계약B"})

    resp = await auth_client.get("/api/v1/contracts/list")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_get_contract(auth_client):
    """계약 상세 조회"""
    create_resp = await auth_client.post("/api/v1/contracts/save", json={"contract_name": "상세 조회"})
    contract_id = create_resp.json()["id"]

    resp = await auth_client.get(f"/api/v1/contracts/{contract_id}")
    assert resp.status_code == 200
    assert resp.json()["contract_name"] == "상세 조회"


@pytest.mark.asyncio
async def test_get_contract_not_found(auth_client):
    """존재하지 않는 계약 조회"""
    resp = await auth_client.get("/api/v1/contracts/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_contract(auth_client):
    """계약 수정"""
    create_resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "수정 전",
        "company_name": "기업A",
    })
    contract_id = create_resp.json()["id"]

    resp = await auth_client.put(f"/api/v1/contracts/{contract_id}", json={
        "contract_name": "수정 후",
        "company_name": "기업B",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["contract_name"] == "수정 후"
    assert data["company_name"] == "기업B"


@pytest.mark.asyncio
async def test_update_contract_duplicate_name(auth_client):
    """계약 수정 시 중복 이름 거부"""
    await auth_client.post("/api/v1/contracts/save", json={"contract_name": "기존 계약"})
    create_resp = await auth_client.post("/api/v1/contracts/save", json={"contract_name": "수정할 계약"})
    contract_id = create_resp.json()["id"]

    resp = await auth_client.put(f"/api/v1/contracts/{contract_id}", json={
        "contract_name": "기존 계약",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_delete_contract(auth_client):
    """계약 삭제"""
    create_resp = await auth_client.post("/api/v1/contracts/save", json={"contract_name": "삭제 대상"})
    contract_id = create_resp.json()["id"]

    resp = await auth_client.delete(f"/api/v1/contracts/{contract_id}")
    assert resp.status_code == 200

    # 삭제 후 조회 시 404
    resp = await auth_client.get(f"/api/v1/contracts/{contract_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_task(auth_client):
    """업무 추가"""
    create_resp = await auth_client.post("/api/v1/contracts/save", json={"contract_name": "업무 테스트"})
    contract_id = create_resp.json()["id"]

    resp = await auth_client.post(f"/api/v1/contracts/{contract_id}/tasks", json={
        "task_name": "새 업무",
        "phase": "1단계",
        "due_date": "2025-06-01",
        "priority": "높음",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["task"]["task_name"] == "새 업무"
    assert data["task"]["task_id"].startswith("TASK-")


@pytest.mark.asyncio
async def test_add_standalone_task(auth_client):
    """미분류 업무 추가"""
    resp = await auth_client.post("/api/v1/contracts/tasks/add", json={
        "task_name": "독립 업무",
    })
    assert resp.status_code == 200
    assert resp.json()["task"]["contract_name"] == "미분류"


@pytest.mark.asyncio
async def test_update_task_status(auth_client):
    """업무 상태 변경"""
    create_resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "상태 테스트",
        "tasks": [{"task_id": "TASK-001", "task_name": "업무", "status": "대기", "priority": "보통", "phase": "", "due_date": ""}],
    })
    contract_id = create_resp.json()["id"]

    resp = await auth_client.patch(f"/api/v1/contracts/{contract_id}/tasks/status", json={
        "task_id": "TASK-001",
        "status": "진행중",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "진행중"


@pytest.mark.asyncio
async def test_update_task_note(auth_client):
    """업무 노트 수정"""
    create_resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "노트 테스트",
        "tasks": [{"task_id": "TASK-001", "task_name": "업무", "status": "대기", "priority": "보통", "phase": "", "due_date": ""}],
    })
    contract_id = create_resp.json()["id"]

    resp = await auth_client.patch(f"/api/v1/contracts/{contract_id}/tasks/note", json={
        "task_id": "TASK-001",
        "note": "처리 완료",
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_summary(auth_client):
    """대시보드 요약"""
    await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "대시보드 테스트",
        "tasks": [
            {"task_id": "TASK-001", "task_name": "업무1", "status": "대기", "priority": "높음", "phase": "", "due_date": "2025-01-01"},
            {"task_id": "TASK-002", "task_name": "업무2", "status": "진행중", "priority": "보통", "phase": "", "due_date": "2025-02-01"},
        ],
    })

    resp = await auth_client.get("/api/v1/contracts/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_contracts"] == 1
    assert data["total_tasks"] == 2
    assert data["pending_tasks"] == 1
    assert data["in_progress_tasks"] == 1


@pytest.mark.asyncio
async def test_unauthenticated_contract_access(client):
    """미인증 계약 접근 거부"""
    resp = await client.get("/api/v1/contracts/list")
    assert resp.status_code == 401

    resp = await client.post("/api/v1/contracts/save", json={"contract_name": "X"})
    assert resp.status_code == 401
