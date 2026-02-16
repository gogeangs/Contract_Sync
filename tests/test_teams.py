"""팀(조직) 시스템 + 업무 담당자 지정 테스트"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from tests.conftest import TestSessionLocal, app
from app.database import User, VerificationCode, Team, TeamMember


# ============ 헬퍼 ============

async def create_user(ac: AsyncClient, email: str, password: str = "test1234") -> AsyncClient:
    """사용자 생성 + 로그인 완료된 클라이언트 반환"""
    await ac.post("/api/v1/auth/send-code", json={"email": email})

    async with TestSessionLocal() as db:
        result = await db.execute(
            select(VerificationCode).where(VerificationCode.email == email)
        )
        code = result.scalar_one().code

    await ac.post("/api/v1/auth/verify-code", json={"email": email, "code": code})
    await ac.post("/api/v1/auth/signup", json={
        "email": email,
        "password": password,
        "password_confirm": password,
    })
    return ac


async def make_auth_client(email: str) -> AsyncClient:
    """새 인증 클라이언트 생성"""
    transport = ASGITransport(app=app)
    ac = AsyncClient(transport=transport, base_url="http://test")
    await create_user(ac, email)
    return ac


# ============ 팀 CRUD 테스트 ============

@pytest.mark.asyncio
async def test_create_team(auth_client):
    """팀 생성"""
    resp = await auth_client.post("/api/v1/teams", json={"name": "개발팀", "description": "개발 조직"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "개발팀"
    assert data["role"] == "owner"
    assert data["id"] > 0


@pytest.mark.asyncio
async def test_list_teams(auth_client):
    """팀 목록 조회"""
    await auth_client.post("/api/v1/teams", json={"name": "팀A"})
    await auth_client.post("/api/v1/teams", json={"name": "팀B"})

    resp = await auth_client.get("/api/v1/teams")
    assert resp.status_code == 200
    teams = resp.json()
    assert len(teams) == 2
    assert teams[0]["name"] == "팀A"


@pytest.mark.asyncio
async def test_get_team_detail(auth_client):
    """팀 상세 조회 + 멤버 목록"""
    create_resp = await auth_client.post("/api/v1/teams", json={"name": "상세팀"})
    team_id = create_resp.json()["id"]

    resp = await auth_client.get(f"/api/v1/teams/{team_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "상세팀"
    assert data["my_role"] == "owner"
    assert len(data["members"]) == 1  # 생성자만


@pytest.mark.asyncio
async def test_update_team(auth_client):
    """팀 정보 수정"""
    create_resp = await auth_client.post("/api/v1/teams", json={"name": "수정전"})
    team_id = create_resp.json()["id"]

    resp = await auth_client.put(f"/api/v1/teams/{team_id}", json={"name": "수정후"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "수정후"


@pytest.mark.asyncio
async def test_delete_team(auth_client):
    """팀 삭제"""
    create_resp = await auth_client.post("/api/v1/teams", json={"name": "삭제팀"})
    team_id = create_resp.json()["id"]

    resp = await auth_client.delete(f"/api/v1/teams/{team_id}")
    assert resp.status_code == 200

    # 삭제 확인
    resp2 = await auth_client.get(f"/api/v1/teams/{team_id}")
    assert resp2.status_code == 403  # 멤버가 아님 (삭제됨)


# ============ 멤버 관리 테스트 ============

@pytest.mark.asyncio
async def test_invite_member(auth_client):
    """멤버 초대"""
    # 두 번째 사용자 생성
    user2 = await make_auth_client("user2@example.com")

    # 팀 생성
    create_resp = await auth_client.post("/api/v1/teams", json={"name": "초대팀"})
    team_id = create_resp.json()["id"]

    # 멤버 초대
    resp = await auth_client.post(
        f"/api/v1/teams/{team_id}/members",
        json={"email": "user2@example.com"}
    )
    assert resp.status_code == 200
    assert resp.json()["member"]["email"] == "user2@example.com"

    # 멤버 목록 확인
    detail_resp = await auth_client.get(f"/api/v1/teams/{team_id}")
    assert len(detail_resp.json()["members"]) == 2

    await user2.aclose()


@pytest.mark.asyncio
async def test_invite_duplicate_member(auth_client):
    """중복 멤버 초대 실패"""
    user2 = await make_auth_client("dup@example.com")

    create_resp = await auth_client.post("/api/v1/teams", json={"name": "중복팀"})
    team_id = create_resp.json()["id"]

    await auth_client.post(f"/api/v1/teams/{team_id}/members", json={"email": "dup@example.com"})
    # 두 번째 초대 - 409
    resp = await auth_client.post(f"/api/v1/teams/{team_id}/members", json={"email": "dup@example.com"})
    assert resp.status_code == 409

    await user2.aclose()


@pytest.mark.asyncio
async def test_remove_member(auth_client):
    """멤버 제거"""
    user2 = await make_auth_client("remove@example.com")

    create_resp = await auth_client.post("/api/v1/teams", json={"name": "제거팀"})
    team_id = create_resp.json()["id"]

    await auth_client.post(f"/api/v1/teams/{team_id}/members", json={"email": "remove@example.com"})

    # user2의 ID 조회
    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "remove@example.com"))
        user2_id = result.scalar_one().id

    resp = await auth_client.delete(f"/api/v1/teams/{team_id}/members/{user2_id}")
    assert resp.status_code == 200

    # 멤버 수 확인
    detail = await auth_client.get(f"/api/v1/teams/{team_id}")
    assert len(detail.json()["members"]) == 1

    await user2.aclose()


@pytest.mark.asyncio
async def test_update_member_role(auth_client):
    """멤버 역할 변경"""
    user2 = await make_auth_client("role@example.com")

    create_resp = await auth_client.post("/api/v1/teams", json={"name": "역할팀"})
    team_id = create_resp.json()["id"]

    await auth_client.post(f"/api/v1/teams/{team_id}/members", json={"email": "role@example.com"})

    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "role@example.com"))
        user2_id = result.scalar_one().id

    resp = await auth_client.patch(
        f"/api/v1/teams/{team_id}/members/{user2_id}/role",
        json={"role": "admin"}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

    await user2.aclose()


# ============ 팀 계약 접근 제어 테스트 ============

@pytest.mark.asyncio
async def test_team_contract_access(auth_client):
    """팀 계약은 팀 멤버만 접근 가능"""
    user2 = await make_auth_client("access@example.com")

    # 팀 생성 + 멤버 초대
    create_resp = await auth_client.post("/api/v1/teams", json={"name": "접근팀"})
    team_id = create_resp.json()["id"]
    await auth_client.post(f"/api/v1/teams/{team_id}/members", json={"email": "access@example.com"})

    # 팀 계약 생성
    contract_resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "팀 계약서",
        "team_id": team_id,
    })
    assert contract_resp.status_code == 200
    contract_id = contract_resp.json()["id"]

    # user2도 팀 계약 조회 가능
    detail = await user2.get(f"/api/v1/contracts/{contract_id}")
    assert detail.status_code == 200
    assert detail.json()["contract_name"] == "팀 계약서"

    await user2.aclose()


@pytest.mark.asyncio
async def test_non_member_cannot_access_team_contract(auth_client):
    """비멤버는 팀 계약 접근 불가"""
    outsider = await make_auth_client("outsider@example.com")

    create_resp = await auth_client.post("/api/v1/teams", json={"name": "비공개팀"})
    team_id = create_resp.json()["id"]

    contract_resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "비공개 계약",
        "team_id": team_id,
    })
    contract_id = contract_resp.json()["id"]

    # 비멤버 접근 실패
    detail = await outsider.get(f"/api/v1/contracts/{contract_id}")
    assert detail.status_code == 404

    await outsider.aclose()


@pytest.mark.asyncio
async def test_personal_contract_not_visible_to_team(auth_client):
    """개인 계약은 팀 목록에 안 보임"""
    # 개인 계약 생성
    await auth_client.post("/api/v1/contracts/save", json={"contract_name": "개인 계약"})

    # 팀 생성
    create_resp = await auth_client.post("/api/v1/teams", json={"name": "필터팀"})
    team_id = create_resp.json()["id"]

    # 팀 필터로 조회 시 개인 계약 안 보임
    resp = await auth_client.get(f"/api/v1/contracts/list?team_id={team_id}")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ============ 담당자 지정 테스트 ============

@pytest.mark.asyncio
async def test_assign_task(auth_client):
    """업무 담당자 지정"""
    # 팀 + 계약 생성
    create_resp = await auth_client.post("/api/v1/teams", json={"name": "담당팀"})
    team_id = create_resp.json()["id"]

    contract_resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "담당 계약",
        "team_id": team_id,
        "tasks": [{"task_id": "TASK-001", "task_name": "테스트업무", "priority": "보통", "status": "대기"}],
    })
    contract_id = contract_resp.json()["id"]

    # 자신의 ID 조회
    me_resp = await auth_client.get("/api/v1/auth/me")
    my_id = me_resp.json()["user"]["id"]

    # 담당자 지정
    resp = await auth_client.patch(
        f"/api/v1/contracts/{contract_id}/tasks/assignee",
        json={"task_id": "TASK-001", "assignee_id": my_id}
    )
    assert resp.status_code == 200
    assert resp.json()["assignee_id"] == my_id

    # 계약 조회하여 담당자 확인
    detail = await auth_client.get(f"/api/v1/contracts/{contract_id}")
    task = detail.json()["tasks"][0]
    assert task["assignee_id"] == my_id
    assert task["assignee_name"] is not None


@pytest.mark.asyncio
async def test_unassign_task(auth_client):
    """업무 담당자 해제"""
    create_resp = await auth_client.post("/api/v1/teams", json={"name": "해제팀"})
    team_id = create_resp.json()["id"]

    me_resp = await auth_client.get("/api/v1/auth/me")
    my_id = me_resp.json()["user"]["id"]

    contract_resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "해제 계약",
        "team_id": team_id,
        "tasks": [{"task_id": "TASK-001", "task_name": "해제업무", "priority": "보통", "status": "대기", "assignee_id": my_id}],
    })
    contract_id = contract_resp.json()["id"]

    # 담당자 해제
    resp = await auth_client.patch(
        f"/api/v1/contracts/{contract_id}/tasks/assignee",
        json={"task_id": "TASK-001", "assignee_id": None}
    )
    assert resp.status_code == 200
    assert resp.json()["assignee_id"] is None


@pytest.mark.asyncio
async def test_add_task_with_assignee(auth_client):
    """업무 추가 시 담당자 지정"""
    create_resp = await auth_client.post("/api/v1/teams", json={"name": "추가팀"})
    team_id = create_resp.json()["id"]

    me_resp = await auth_client.get("/api/v1/auth/me")
    my_id = me_resp.json()["user"]["id"]

    contract_resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "추가 계약",
        "team_id": team_id,
    })
    contract_id = contract_resp.json()["id"]

    resp = await auth_client.post(
        f"/api/v1/contracts/{contract_id}/tasks",
        json={"task_name": "담당업무", "assignee_id": my_id}
    )
    assert resp.status_code == 200
    task = resp.json()["task"]
    assert task["assignee_id"] == my_id


@pytest.mark.asyncio
async def test_non_member_cannot_be_assignee(auth_client):
    """비멤버는 담당자로 지정 불가"""
    outsider = await make_auth_client("notmember@example.com")

    create_resp = await auth_client.post("/api/v1/teams", json={"name": "검증팀"})
    team_id = create_resp.json()["id"]

    contract_resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "검증 계약",
        "team_id": team_id,
        "tasks": [{"task_id": "TASK-001", "task_name": "검증업무", "priority": "보통", "status": "대기"}],
    })
    contract_id = contract_resp.json()["id"]

    # 비멤버 ID
    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "notmember@example.com"))
        outsider_id = result.scalar_one().id

    resp = await auth_client.patch(
        f"/api/v1/contracts/{contract_id}/tasks/assignee",
        json={"task_id": "TASK-001", "assignee_id": outsider_id}
    )
    assert resp.status_code == 400

    await outsider.aclose()


# ============ auth/me 팀 목록 테스트 ============

@pytest.mark.asyncio
async def test_auth_me_includes_teams(auth_client):
    """auth/me 응답에 팀 목록 포함"""
    await auth_client.post("/api/v1/teams", json={"name": "ME팀"})

    resp = await auth_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "teams" in data
    assert len(data["teams"]) == 1
    assert data["teams"][0]["name"] == "ME팀"
    assert data["teams"][0]["role"] == "owner"


# ============ 기존 개인 계약 하위 호환 테스트 ============

@pytest.mark.asyncio
async def test_personal_contract_still_works(auth_client):
    """기존 개인 계약 생성/조회가 정상 동작"""
    # team_id 없이 계약 생성 (기존 방식)
    resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "하위호환 계약",
    })
    assert resp.status_code == 200
    contract_id = resp.json()["id"]
    assert resp.json()["team_id"] is None

    # 목록 조회
    list_resp = await auth_client.get("/api/v1/contracts/list")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1

    # 상세 조회
    detail_resp = await auth_client.get(f"/api/v1/contracts/{contract_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["contract_name"] == "하위호환 계약"
