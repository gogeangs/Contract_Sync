"""v2 프로젝트 + 업무 API 테스트 (구 test_contracts.py → v2 전환)"""
import pytest


@pytest.mark.asyncio
async def test_create_project(auth_client):
    """프로젝트 생성"""
    resp = await auth_client.post("/api/v1/projects", json={
        "project_name": "테스트 프로젝트",
        "project_type": "internal",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_name"] == "테스트 프로젝트"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_list_projects(auth_client):
    """프로젝트 목록 조회"""
    await auth_client.post("/api/v1/projects", json={"project_name": "프로젝트A", "project_type": "internal"})
    await auth_client.post("/api/v1/projects", json={"project_name": "프로젝트B", "project_type": "internal"})

    resp = await auth_client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["projects"]) == 2


@pytest.mark.asyncio
async def test_list_projects_pagination(auth_client):
    """프로젝트 목록 페이지네이션"""
    for i in range(3):
        await auth_client.post("/api/v1/projects", json={"project_name": f"페이지 프로젝트{i}", "project_type": "internal"})

    resp = await auth_client.get("/api/v1/projects?page=1&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["projects"]) == 2

    resp2 = await auth_client.get("/api/v1/projects?page=2&size=2")
    assert len(resp2.json()["projects"]) == 1


@pytest.mark.asyncio
async def test_get_project(auth_client):
    """프로젝트 상세 조회"""
    create_resp = await auth_client.post("/api/v1/projects", json={"project_name": "상세 조회", "project_type": "internal"})
    project_id = create_resp.json()["id"]

    resp = await auth_client.get(f"/api/v1/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["project_name"] == "상세 조회"


@pytest.mark.asyncio
async def test_get_project_not_found(auth_client):
    """존재하지 않는 프로젝트 조회"""
    resp = await auth_client.get("/api/v1/projects/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_project(auth_client):
    """프로젝트 수정"""
    create_resp = await auth_client.post("/api/v1/projects", json={
        "project_name": "수정 전",
        "project_type": "internal",
        "description": "설명A",
    })
    project_id = create_resp.json()["id"]

    resp = await auth_client.put(f"/api/v1/projects/{project_id}", json={
        "project_name": "수정 후",
        "description": "설명B",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_name"] == "수정 후"
    assert data["description"] == "설명B"


@pytest.mark.asyncio
async def test_delete_project(auth_client):
    """프로젝트 삭제"""
    create_resp = await auth_client.post("/api/v1/projects", json={"project_name": "삭제 대상", "project_type": "internal"})
    project_id = create_resp.json()["id"]

    resp = await auth_client.delete(f"/api/v1/projects/{project_id}")
    assert resp.status_code == 200

    resp = await auth_client.get(f"/api/v1/projects/{project_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_task(auth_client):
    """업무 생성"""
    proj_resp = await auth_client.post("/api/v1/projects", json={"project_name": "업무 테스트", "project_type": "internal"})
    project_id = proj_resp.json()["id"]

    resp = await auth_client.post("/api/v1/tasks", json={
        "task_name": "새 업무",
        "project_id": project_id,
        "phase": "1단계",
        "due_date": "2025-06-01",
        "priority": "높음",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_name"] == "새 업무"
    assert data["task_code"] is not None


@pytest.mark.asyncio
async def test_create_standalone_task(auth_client):
    """독립 업무 생성 (프로젝트 없이)"""
    resp = await auth_client.post("/api/v1/tasks", json={
        "task_name": "독립 업무",
    })
    assert resp.status_code == 200
    assert resp.json()["project_id"] is None


@pytest.mark.asyncio
async def test_update_task_status(auth_client):
    """업무 상태 변경"""
    resp = await auth_client.post("/api/v1/tasks", json={
        "task_name": "상태 테스트",
        "priority": "보통",
    })
    task_id = resp.json()["id"]

    resp = await auth_client.patch(f"/api/v1/tasks/{task_id}/status", json={
        "status": "in_progress",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_update_task_note(auth_client):
    """업무 노트 수정"""
    resp = await auth_client.post("/api/v1/tasks", json={"task_name": "노트 테스트"})
    task_id = resp.json()["id"]

    resp = await auth_client.patch(f"/api/v1/tasks/{task_id}/note", json={
        "note": "처리 완료",
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_task(auth_client):
    """업무 삭제"""
    resp = await auth_client.post("/api/v1/tasks", json={"task_name": "삭제 업무"})
    task_id = resp.json()["id"]

    resp = await auth_client.delete(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200

    resp = await auth_client.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dashboard_summary(auth_client):
    """대시보드 요약"""
    proj_resp = await auth_client.post("/api/v1/projects", json={
        "project_name": "대시보드 테스트",
        "project_type": "internal",
    })
    project_id = proj_resp.json()["id"]

    # 프로젝트를 active로 변경
    await auth_client.patch(f"/api/v1/projects/{project_id}/status", json={"status": "active"})

    await auth_client.post("/api/v1/tasks", json={
        "task_name": "업무1", "project_id": project_id, "priority": "높음",
    })
    await auth_client.post("/api/v1/tasks", json={
        "task_name": "업무2", "project_id": project_id, "priority": "보통",
    })

    resp = await auth_client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_projects"] == 1
    assert data["pending_tasks"] == 2


@pytest.mark.asyncio
async def test_unauthenticated_project_access(client):
    """미인증 프로젝트 접근 거부"""
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 401

    resp = await client.post("/api/v1/projects", json={"project_name": "X"})
    assert resp.status_code == 401
