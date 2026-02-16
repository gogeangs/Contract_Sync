"""
테스트: 3. 댓글, 4. 알림, 5. 활동 로그, 6. 세분화된 권한 관리
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from tests.conftest import TestSessionLocal, override_get_db

from app.main import app


async def create_user(email: str, password: str = "test1234") -> AsyncClient:
    """사용자 생성 + 로그인된 클라이언트 반환"""
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    await client.post("/api/v1/auth/send-code", json={"email": email})

    async with TestSessionLocal() as db:
        from sqlalchemy import select
        from app.database import VerificationCode
        result = await db.execute(
            select(VerificationCode).where(VerificationCode.email == email)
        )
        code = result.scalar_one().code

    await client.post("/api/v1/auth/verify-code", json={"email": email, "code": code})
    await client.post("/api/v1/auth/signup", json={
        "email": email, "password": password, "password_confirm": password,
    })
    return client


# ============ 3. 댓글 시스템 ============

@pytest.mark.asyncio
async def test_create_comment(auth_client):
    """댓글 작성"""
    # 계약 생성
    resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "댓글 테스트 계약",
        "tasks": [{"task_id": "TASK-001", "task_name": "테스트 업무", "status": "대기"}],
    })
    contract_id = resp.json()["id"]

    # 계약 전체 댓글 작성
    resp = await auth_client.post(f"/api/v1/contracts/{contract_id}/comments", json={
        "content": "계약 관련 질문입니다.",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "계약 관련 질문입니다."
    assert data["is_mine"] is True


@pytest.mark.asyncio
async def test_create_task_comment(auth_client):
    """업무 댓글 작성"""
    resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "업무 댓글 테스트",
        "tasks": [{"task_id": "TASK-001", "task_name": "업무1", "status": "대기"}],
    })
    contract_id = resp.json()["id"]

    # 업무에 댓글 작성
    resp = await auth_client.post(f"/api/v1/contracts/{contract_id}/comments", json={
        "content": "업무 관련 댓글",
        "task_id": "TASK-001",
    })
    assert resp.status_code == 200
    assert resp.json()["task_id"] == "TASK-001"


@pytest.mark.asyncio
async def test_list_comments(auth_client):
    """댓글 목록 조회"""
    resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "댓글 목록 테스트",
    })
    contract_id = resp.json()["id"]

    # 댓글 2개 작성
    await auth_client.post(f"/api/v1/contracts/{contract_id}/comments", json={"content": "첫번째"})
    await auth_client.post(f"/api/v1/contracts/{contract_id}/comments", json={"content": "두번째"})

    # 목록 조회
    resp = await auth_client.get(f"/api/v1/contracts/{contract_id}/comments")
    assert resp.status_code == 200
    comments = resp.json()
    assert len(comments) == 2


@pytest.mark.asyncio
async def test_update_comment(auth_client):
    """댓글 수정"""
    resp = await auth_client.post("/api/v1/contracts/save", json={"contract_name": "수정 테스트"})
    contract_id = resp.json()["id"]

    resp = await auth_client.post(f"/api/v1/contracts/{contract_id}/comments", json={"content": "원본"})
    comment_id = resp.json()["id"]

    resp = await auth_client.put(f"/api/v1/contracts/{contract_id}/comments/{comment_id}", json={"content": "수정됨"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "수정됨"


@pytest.mark.asyncio
async def test_delete_comment(auth_client):
    """댓글 삭제"""
    resp = await auth_client.post("/api/v1/contracts/save", json={"contract_name": "삭제 테스트"})
    contract_id = resp.json()["id"]

    resp = await auth_client.post(f"/api/v1/contracts/{contract_id}/comments", json={"content": "삭제할 댓글"})
    comment_id = resp.json()["id"]

    resp = await auth_client.delete(f"/api/v1/contracts/{contract_id}/comments/{comment_id}")
    assert resp.status_code == 200

    # 삭제 확인
    resp = await auth_client.get(f"/api/v1/contracts/{contract_id}/comments")
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_cannot_edit_others_comment():
    """타인 댓글 수정 불가"""
    user1 = await create_user("comment_user1@test.com")
    user2 = await create_user("comment_user2@test.com")

    try:
        # user1이 팀 생성
        resp = await user1.post("/api/v1/teams", json={"name": "댓글팀"})
        team_id = resp.json()["id"]

        # user2 초대
        await user1.post(f"/api/v1/teams/{team_id}/members", json={"email": "comment_user2@test.com"})

        # user1이 팀 계약 생성
        resp = await user1.post("/api/v1/contracts/save", json={
            "contract_name": "팀 댓글 계약", "team_id": team_id,
        })
        contract_id = resp.json()["id"]

        # user1이 댓글 작성
        resp = await user1.post(f"/api/v1/contracts/{contract_id}/comments", json={"content": "user1 댓글"})
        comment_id = resp.json()["id"]

        # user2가 수정 시도 -> 403
        resp = await user2.put(f"/api/v1/contracts/{contract_id}/comments/{comment_id}", json={"content": "수정"})
        assert resp.status_code == 403
    finally:
        await user1.aclose()
        await user2.aclose()


# ============ 4. 알림 시스템 ============

@pytest.mark.asyncio
async def test_notification_on_team_comment():
    """팀 댓글 시 알림 생성"""
    user1 = await create_user("notif_user1@test.com")
    user2 = await create_user("notif_user2@test.com")

    try:
        resp = await user1.post("/api/v1/teams", json={"name": "알림팀"})
        team_id = resp.json()["id"]
        await user1.post(f"/api/v1/teams/{team_id}/members", json={"email": "notif_user2@test.com"})

        resp = await user1.post("/api/v1/contracts/save", json={
            "contract_name": "알림 테스트 계약", "team_id": team_id,
        })
        contract_id = resp.json()["id"]

        # user1이 댓글 작성
        await user1.post(f"/api/v1/contracts/{contract_id}/comments", json={"content": "알림 테스트"})

        # user2에게 알림이 왔는지 확인
        resp = await user2.get("/api/v1/notifications/unread-count")
        assert resp.status_code == 200
        assert resp.json()["unread_count"] >= 1

        resp = await user2.get("/api/v1/notifications")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(n["type"] == "comment" for n in items)
    finally:
        await user1.aclose()
        await user2.aclose()


@pytest.mark.asyncio
async def test_notification_on_assign():
    """담당자 지정 시 알림"""
    user1 = await create_user("assign_n1@test.com")
    user2 = await create_user("assign_n2@test.com")

    try:
        resp = await user1.post("/api/v1/teams", json={"name": "배정팀"})
        team_id = resp.json()["id"]
        await user1.post(f"/api/v1/teams/{team_id}/members", json={"email": "assign_n2@test.com"})

        # user2의 user_id 구하기
        resp = await user2.get("/api/v1/auth/me")
        user2_id = resp.json()["user"]["id"]

        # 계약 + 업무 생성
        resp = await user1.post("/api/v1/contracts/save", json={
            "contract_name": "배정 알림 계약", "team_id": team_id,
            "tasks": [{"task_id": "TASK-001", "task_name": "배정업무", "status": "대기"}],
        })
        contract_id = resp.json()["id"]

        # user1이 user2를 담당자로 지정
        resp = await user1.patch(f"/api/v1/contracts/{contract_id}/tasks/assignee", json={
            "task_id": "TASK-001", "assignee_id": user2_id,
        })
        assert resp.status_code == 200

        # user2에게 assign 알림 확인
        resp = await user2.get("/api/v1/notifications")
        items = resp.json()["items"]
        assert any(n["type"] == "assign" for n in items)
    finally:
        await user1.aclose()
        await user2.aclose()


@pytest.mark.asyncio
async def test_mark_notification_read(auth_client):
    """알림 읽음 처리"""
    # 알림이 없으면 빈 목록
    resp = await auth_client.get("/api/v1/notifications")
    assert resp.status_code == 200

    # 읽지 않은 개수
    resp = await auth_client.get("/api/v1/notifications/unread-count")
    assert resp.status_code == 200
    assert "unread_count" in resp.json()


@pytest.mark.asyncio
async def test_mark_all_read(auth_client):
    """모든 알림 읽음 처리"""
    resp = await auth_client.patch("/api/v1/notifications/read-all")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_notification_on_team_invite():
    """팀 초대 시 알림"""
    user1 = await create_user("invite_n1@test.com")
    user2 = await create_user("invite_n2@test.com")

    try:
        resp = await user1.post("/api/v1/teams", json={"name": "초대알림팀"})
        team_id = resp.json()["id"]
        await user1.post(f"/api/v1/teams/{team_id}/members", json={"email": "invite_n2@test.com"})

        # user2에게 team_invite 알림
        resp = await user2.get("/api/v1/notifications")
        items = resp.json()["items"]
        assert any(n["type"] == "team_invite" for n in items)
    finally:
        await user1.aclose()
        await user2.aclose()


# ============ 5. 활동 로그 ============

@pytest.mark.asyncio
async def test_activity_log_on_contract_create(auth_client):
    """계약 생성 시 활동 로그"""
    await auth_client.post("/api/v1/contracts/save", json={"contract_name": "활동로그 계약"})

    resp = await auth_client.get("/api/v1/activity")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(l["action"] == "create" and l["target_type"] == "contract" for l in items)


@pytest.mark.asyncio
async def test_activity_log_on_task_status_change(auth_client):
    """업무 상태 변경 시 활동 로그"""
    resp = await auth_client.post("/api/v1/contracts/save", json={
        "contract_name": "상태변경 로그",
        "tasks": [{"task_id": "TASK-001", "task_name": "로그업무", "status": "대기"}],
    })
    contract_id = resp.json()["id"]

    await auth_client.patch(f"/api/v1/contracts/{contract_id}/tasks/status", json={
        "task_id": "TASK-001", "status": "진행중",
    })

    resp = await auth_client.get(f"/api/v1/activity?contract_id={contract_id}")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(l["action"] == "status_change" for l in items)


@pytest.mark.asyncio
async def test_activity_log_on_team_actions():
    """팀 관련 활동 로그"""
    user1 = await create_user("log_user1@test.com")
    user2 = await create_user("log_user2@test.com")

    try:
        resp = await user1.post("/api/v1/teams", json={"name": "로그팀"})
        team_id = resp.json()["id"]

        await user1.post(f"/api/v1/teams/{team_id}/members", json={"email": "log_user2@test.com"})

        resp = await user1.get(f"/api/v1/activity?team_id={team_id}")
        assert resp.status_code == 200
        items = resp.json()["items"]
        # 팀 생성 + 멤버 초대 로그
        assert any(l["action"] == "create" and l["target_type"] == "team" for l in items)
        assert any(l["action"] == "invite" and l["target_type"] == "member" for l in items)
    finally:
        await user1.aclose()
        await user2.aclose()


@pytest.mark.asyncio
async def test_activity_log_on_comment(auth_client):
    """댓글 작성 시 활동 로그"""
    resp = await auth_client.post("/api/v1/contracts/save", json={"contract_name": "댓글로그계약"})
    contract_id = resp.json()["id"]

    await auth_client.post(f"/api/v1/contracts/{contract_id}/comments", json={"content": "활동로그테스트"})

    resp = await auth_client.get(f"/api/v1/activity?contract_id={contract_id}")
    items = resp.json()["items"]
    assert any(l["action"] == "comment" for l in items)


# ============ 6. 세분화된 권한 관리 ============

@pytest.mark.asyncio
async def test_permissions_endpoint():
    """권한 확인 API"""
    user1 = await create_user("perm_user1@test.com")
    user2 = await create_user("perm_user2@test.com")

    try:
        resp = await user1.post("/api/v1/teams", json={"name": "권한팀"})
        team_id = resp.json()["id"]
        await user1.post(f"/api/v1/teams/{team_id}/members", json={"email": "perm_user2@test.com"})

        # owner 권한
        resp = await user1.get(f"/api/v1/teams/{team_id}/permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "owner"
        assert "team.delete" in data["permissions"]
        assert "contract.delete" in data["permissions"]

        # member 권한
        resp = await user2.get(f"/api/v1/teams/{team_id}/permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "member"
        assert "team.delete" not in data["permissions"]
        assert "contract.create" in data["permissions"]
    finally:
        await user1.aclose()
        await user2.aclose()


@pytest.mark.asyncio
async def test_viewer_role_permissions():
    """viewer 역할 권한"""
    user1 = await create_user("viewer_owner@test.com")
    user2 = await create_user("viewer_user@test.com")

    try:
        resp = await user1.post("/api/v1/teams", json={"name": "뷰어팀"})
        team_id = resp.json()["id"]
        await user1.post(f"/api/v1/teams/{team_id}/members", json={"email": "viewer_user@test.com"})

        # user2의 id 조회
        resp = await user2.get("/api/v1/auth/me")
        user2_id = resp.json()["user"]["id"]

        # viewer로 역할 변경
        resp = await user1.patch(f"/api/v1/teams/{team_id}/members/{user2_id}/role", json={"role": "viewer"})
        assert resp.status_code == 200

        # viewer 권한 확인
        resp = await user2.get(f"/api/v1/teams/{team_id}/permissions")
        data = resp.json()
        assert data["role"] == "viewer"
        assert "comment.create" in data["permissions"]
        assert "contract.create" not in data["permissions"]
        assert "task.create" not in data["permissions"]
    finally:
        await user1.aclose()
        await user2.aclose()


@pytest.mark.asyncio
async def test_team_detail_includes_permissions():
    """팀 상세에 my_permissions 포함"""
    user1 = await create_user("detail_perm@test.com")

    try:
        resp = await user1.post("/api/v1/teams", json={"name": "상세권한팀"})
        team_id = resp.json()["id"]

        resp = await user1.get(f"/api/v1/teams/{team_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "my_permissions" in data
        assert "my_role" in data
        assert data["my_role"] == "owner"
    finally:
        await user1.aclose()


@pytest.mark.asyncio
async def test_admin_can_delete_others_comment():
    """admin/owner는 타인 댓글 삭제 가능"""
    user1 = await create_user("admin_del1@test.com")
    user2 = await create_user("admin_del2@test.com")

    try:
        resp = await user1.post("/api/v1/teams", json={"name": "삭제권한팀"})
        team_id = resp.json()["id"]
        await user1.post(f"/api/v1/teams/{team_id}/members", json={"email": "admin_del2@test.com"})

        resp = await user1.post("/api/v1/contracts/save", json={
            "contract_name": "삭제권한계약", "team_id": team_id,
        })
        contract_id = resp.json()["id"]

        # user2가 댓글 작성
        resp = await user2.post(f"/api/v1/contracts/{contract_id}/comments", json={"content": "멤버 댓글"})
        comment_id = resp.json()["id"]

        # user1(owner)이 user2의 댓글 삭제
        resp = await user1.delete(f"/api/v1/contracts/{contract_id}/comments/{comment_id}")
        assert resp.status_code == 200
    finally:
        await user1.aclose()
        await user2.aclose()


@pytest.mark.asyncio
async def test_mention_notification():
    """@멘션 알림"""
    user1 = await create_user("mention1@test.com")
    user2 = await create_user("mention2@test.com")

    try:
        resp = await user1.post("/api/v1/teams", json={"name": "멘션팀"})
        team_id = resp.json()["id"]
        await user1.post(f"/api/v1/teams/{team_id}/members", json={"email": "mention2@test.com"})

        resp = await user1.post("/api/v1/contracts/save", json={
            "contract_name": "멘션 계약", "team_id": team_id,
        })
        contract_id = resp.json()["id"]

        # user1이 user2를 멘션하는 댓글 작성
        await user1.post(f"/api/v1/contracts/{contract_id}/comments", json={
            "content": "확인 부탁드립니다 @mention2@test.com",
        })

        # user2에게 mention 알림
        resp = await user2.get("/api/v1/notifications")
        items = resp.json()["items"]
        assert any(n["type"] == "mention" for n in items)
    finally:
        await user1.aclose()
        await user2.aclose()
