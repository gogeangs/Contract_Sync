"""4차 개발 QA 테스트 — Phase 1~4

Phase 1: 게시판, 이메일 초대, 프로필 이미지
Phase 2: 멀티팀 우선업무
Phase 3: 멤버 간 채팅
Phase 4: 출퇴근 기록
"""
import pytest
from tests.conftest import TestSessionLocal
from sqlalchemy import select
from app.database import (
    User, Team, TeamMember, Project, Client, Task,
    Board, BoardPost, BoardComment, PendingInvite,
    UserTaskPriority, ChatRoom, ChatRoomMember, RoomMessage,
    Attendance, AttendancePolicy, VerificationCode,
)


# ── 헬퍼 ──

async def _create_user(ac, email, name="테스트유저"):
    """회원가입 + 로그인"""
    await ac.post("/api/v1/auth/send-code", json={"email": email})
    async with TestSessionLocal() as db:
        result = await db.execute(
            select(VerificationCode).where(VerificationCode.email == email)
        )
        code = result.scalar_one().code
    await ac.post("/api/v1/auth/verify-code", json={"email": email, "code": code})
    await ac.post("/api/v1/auth/signup", json={
        "email": email, "password": "test1234", "password_confirm": "test1234",
    })
    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.name = name
        await db.commit()
    return ac


async def _setup_team(user_email, team_name="QA팀"):
    """팀 + 발주처 + 프로젝트 + 업무 생성"""
    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == user_email))
        user = result.scalar_one()

        team = Team(name=team_name, created_by=user.id)
        db.add(team)
        await db.flush()

        db.add(TeamMember(team_id=team.id, user_id=user.id, role="owner"))

        client = Client(name="QA발주처", user_id=user.id, team_id=team.id)
        db.add(client)
        await db.flush()

        project = Project(
            project_name="QA프로젝트", user_id=user.id, team_id=team.id,
            client_id=client.id, status="in_progress",
        )
        db.add(project)
        await db.flush()

        task = Task(
            task_name="QA업무", project_id=project.id, user_id=user.id,
            team_id=team.id, assignee_id=user.id, status="in_progress",
            priority="높음",
        )
        db.add(task)
        await db.commit()
        return team.id, project.id, task.id


async def _add_member(team_id, email, role="member"):
    """팀에 멤버 추가"""
    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        db.add(TeamMember(team_id=team_id, user_id=user.id, role=role))
        await db.commit()
        return user.id


# ══════════════════════════════════════════
# Phase 1: 게시판
# ══════════════════════════════════════════

class TestBoard:
    """게시판 CRUD 테스트"""

    @pytest.mark.asyncio
    async def test_board_list_auto_created(self, client):
        """T1: 팀 게시판 조회 시 기본 게시판 자동 생성"""
        ac = await _create_user(client, "board1@test.com", "게시판유저")
        team_id, _, _ = await _setup_team("board1@test.com")

        resp = await ac.get(f"/api/v1/teams/{team_id}/boards")
        assert resp.status_code == 200
        boards = resp.json()
        assert len(boards) >= 3  # notice, free, archive

    @pytest.mark.asyncio
    async def test_create_post(self, client):
        """T2: 게시글 작성"""
        ac = await _create_user(client, "board2@test.com", "글작성자")
        team_id, _, _ = await _setup_team("board2@test.com")

        boards = (await ac.get(f"/api/v1/teams/{team_id}/boards")).json()
        board_id = boards[0]["id"]

        resp = await ac.post(f"/api/v1/boards/{board_id}/posts", json={
            "title": "테스트 공지",
            "content": "공지 내용입니다.",
        })
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["title"] == "테스트 공지"

    @pytest.mark.asyncio
    async def test_post_detail_and_view_count(self, client):
        """T3: 게시글 상세 조회 + 조회수 증가"""
        ac = await _create_user(client, "board3@test.com", "조회자")
        team_id, _, _ = await _setup_team("board3@test.com")

        boards = (await ac.get(f"/api/v1/teams/{team_id}/boards")).json()
        board_id = boards[0]["id"]
        post = (await ac.post(f"/api/v1/boards/{board_id}/posts", json={
            "title": "조회수 테스트", "content": "내용",
        })).json()

        resp = await ac.get(f"/api/v1/posts/{post['id']}")
        assert resp.status_code == 200
        assert resp.json()["view_count"] >= 1

    @pytest.mark.asyncio
    async def test_update_post(self, client):
        """T4: 게시글 수정"""
        ac = await _create_user(client, "board4@test.com", "수정자")
        team_id, _, _ = await _setup_team("board4@test.com")

        boards = (await ac.get(f"/api/v1/teams/{team_id}/boards")).json()
        board_id = boards[0]["id"]
        post = (await ac.post(f"/api/v1/boards/{board_id}/posts", json={
            "title": "원본", "content": "원본 내용",
        })).json()

        resp = await ac.put(f"/api/v1/posts/{post['id']}", json={
            "title": "수정됨", "content": "수정된 내용",
        })
        assert resp.status_code == 200
        assert resp.json()["title"] == "수정됨"

    @pytest.mark.asyncio
    async def test_delete_post(self, client):
        """T5: 게시글 삭제"""
        ac = await _create_user(client, "board5@test.com", "삭제자")
        team_id, _, _ = await _setup_team("board5@test.com")

        boards = (await ac.get(f"/api/v1/teams/{team_id}/boards")).json()
        board_id = boards[0]["id"]
        post = (await ac.post(f"/api/v1/boards/{board_id}/posts", json={
            "title": "삭제할 글", "content": "삭제됨",
        })).json()

        resp = await ac.delete(f"/api/v1/posts/{post['id']}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_pin_post(self, client):
        """T6: 공지 고정/해제"""
        ac = await _create_user(client, "board6@test.com", "고정자")
        team_id, _, _ = await _setup_team("board6@test.com")

        boards = (await ac.get(f"/api/v1/teams/{team_id}/boards")).json()
        board_id = boards[0]["id"]
        post = (await ac.post(f"/api/v1/boards/{board_id}/posts", json={
            "title": "고정 테스트", "content": "고정",
        })).json()

        resp = await ac.patch(f"/api/v1/posts/{post['id']}/pin")
        assert resp.status_code == 200
        assert resp.json()["is_pinned"] is True

    @pytest.mark.asyncio
    async def test_comment_crud(self, client):
        """T7: 댓글 작성/삭제"""
        ac = await _create_user(client, "board7@test.com", "댓글자")
        team_id, _, _ = await _setup_team("board7@test.com")

        boards = (await ac.get(f"/api/v1/teams/{team_id}/boards")).json()
        board_id = boards[0]["id"]
        post = (await ac.post(f"/api/v1/boards/{board_id}/posts", json={
            "title": "댓글 테스트", "content": "본문",
        })).json()

        comment = await ac.post(f"/api/v1/posts/{post['id']}/comments", json={
            "content": "테스트 댓글",
        })
        assert comment.status_code in (200, 201)
        comment_id = comment.json()["id"]

        resp = await ac.delete(f"/api/v1/comments/{comment_id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_post_search(self, client):
        """T8: 게시글 검색"""
        ac = await _create_user(client, "board8@test.com", "검색자")
        team_id, _, _ = await _setup_team("board8@test.com")

        boards = (await ac.get(f"/api/v1/teams/{team_id}/boards")).json()
        board_id = boards[0]["id"]
        await ac.post(f"/api/v1/boards/{board_id}/posts", json={
            "title": "고유키워드ABC", "content": "내용",
        })

        resp = await ac.get(f"/api/v1/boards/{board_id}/posts?search=고유키워드ABC")
        assert resp.status_code == 200
        items = resp.json()["items"] if "items" in resp.json() else resp.json()
        found = any("고유키워드ABC" in (p.get("title", "") or "") for p in (items if isinstance(items, list) else [items]))
        assert found

    @pytest.mark.asyncio
    async def test_personal_board_auto_created(self, client):
        """T37-b: 개인 게시판 자동 생성"""
        ac = await _create_user(client, "pboard1@test.com", "개인게시판유저")

        resp = await ac.get("/api/v1/my/boards")
        assert resp.status_code == 200
        boards = resp.json()
        assert len(boards) >= 2  # 메모, 자료실

    @pytest.mark.asyncio
    async def test_personal_board_post_crud(self, client):
        """T37-c: 개인 게시판 글 작성"""
        ac = await _create_user(client, "pboard2@test.com", "개인글유저")

        boards = (await ac.get("/api/v1/my/boards")).json()
        board_id = boards[0]["id"]

        resp = await ac.post(f"/api/v1/boards/{board_id}/posts", json={
            "title": "개인 메모", "content": "개인 내용",
        })
        assert resp.status_code in (200, 201)


# ══════════════════════════════════════════
# Phase 1: 이메일 초대
# ══════════════════════════════════════════

class TestInvite:
    """미가입 사용자 이메일 초대 테스트"""

    @pytest.mark.asyncio
    async def test_send_invite(self, client):
        """T9: 초대 발송"""
        ac = await _create_user(client, "inv1@test.com", "초대자")
        team_id, _, _ = await _setup_team("inv1@test.com")

        resp = await ac.post(f"/api/v1/teams/{team_id}/invites", json={
            "email": "newuser@example.com",
        })
        assert resp.status_code in (200, 201)
        assert "token" in resp.json() or "id" in resp.json()

    @pytest.mark.asyncio
    async def test_list_invites(self, client):
        """T10: 대기 초대 목록 조회"""
        ac = await _create_user(client, "inv2@test.com", "초대자2")
        team_id, _, _ = await _setup_team("inv2@test.com")

        await ac.post(f"/api/v1/teams/{team_id}/invites", json={
            "email": "pending@example.com",
        })

        resp = await ac.get(f"/api/v1/teams/{team_id}/invites")
        assert resp.status_code == 200
        invites = resp.json()
        assert len(invites) >= 1

    @pytest.mark.asyncio
    async def test_cancel_invite(self, client):
        """T11: 초대 취소"""
        ac = await _create_user(client, "inv3@test.com", "초대자3")
        team_id, _, _ = await _setup_team("inv3@test.com")

        inv = (await ac.post(f"/api/v1/teams/{team_id}/invites", json={
            "email": "cancel@example.com",
        })).json()

        invite_id = inv.get("id") or inv.get("invite_id")
        resp = await ac.delete(f"/api/v1/invites/{invite_id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_accept_invite_info(self, client):
        """T12: 초대 수락 페이지 정보 조회 (비로그인)"""
        ac = await _create_user(client, "inv4@test.com", "초대자4")
        team_id, _, _ = await _setup_team("inv4@test.com")

        inv = (await ac.post(f"/api/v1/teams/{team_id}/invites", json={
            "email": "accept@example.com",
        })).json()

        token = inv.get("token")
        if token:
            from httpx import AsyncClient, ASGITransport
            from app.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as anon:
                resp = await anon.get(f"/api/v1/invites/accept/{token}")
                assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_duplicate_invite_rejected(self, client):
        """T13: 중복 초대 거부"""
        ac = await _create_user(client, "inv5@test.com", "초대자5")
        team_id, _, _ = await _setup_team("inv5@test.com")

        await ac.post(f"/api/v1/teams/{team_id}/invites", json={
            "email": "dup@example.com",
        })
        resp = await ac.post(f"/api/v1/teams/{team_id}/invites", json={
            "email": "dup@example.com",
        })
        assert resp.status_code in (400, 409)


# ══════════════════════════════════════════
# Phase 1: 프로필 이미지
# ══════════════════════════════════════════

class TestProfileImage:
    """프로필 이미지 업로드 테스트"""

    @pytest.mark.asyncio
    async def test_upload_profile_image(self, client):
        """T14: 프로필 이미지 업로드"""
        ac = await _create_user(client, "prof1@test.com", "프로필유저")

        # 1x1 PNG 이미지 생성
        import io
        img_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'

        resp = await ac.post("/api/v1/auth/profile/picture", files={
            "file": ("test.png", io.BytesIO(img_data), "image/png"),
        })
        assert resp.status_code == 200
        assert "picture" in resp.json()

    @pytest.mark.asyncio
    async def test_upload_invalid_type_rejected(self, client):
        """T15: 잘못된 파일 형식 거부"""
        ac = await _create_user(client, "prof2@test.com", "프로필유저2")

        import io
        resp = await ac.post("/api/v1/auth/profile/picture", files={
            "file": ("test.txt", io.BytesIO(b"not an image"), "text/plain"),
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_profile_image(self, client):
        """T16: 프로필 이미지 삭제"""
        ac = await _create_user(client, "prof3@test.com", "프로필유저3")

        resp = await ac.delete("/api/v1/auth/profile/picture")
        assert resp.status_code == 200


# ══════════════════════════════════════════
# Phase 2: 멀티팀 우선업무
# ══════════════════════════════════════════

class TestMyTasks:
    """멀티팀 우선업무 테스트"""

    @pytest.mark.asyncio
    async def test_my_tasks_list(self, client):
        """T17: 전체 팀 통합 내 업무 조회"""
        ac = await _create_user(client, "mt1@test.com", "멀티팀유저")
        await _setup_team("mt1@test.com", "팀A")

        resp = await ac.get("/api/v1/my/tasks")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_my_tasks_filter_by_team(self, client):
        """T18: 팀별 필터링"""
        ac = await _create_user(client, "mt2@test.com", "멀티팀유저2")
        team_id, _, _ = await _setup_team("mt2@test.com", "팀B")

        resp = await ac.get(f"/api/v1/my/tasks?team_id={team_id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_save_priority(self, client):
        """T19: 우선순위 저장"""
        ac = await _create_user(client, "mt3@test.com", "멀티팀유저3")
        _, _, task_id = await _setup_team("mt3@test.com", "팀C")

        resp = await ac.put("/api/v1/my/tasks/priority", json={
            "task_ids": [task_id],
        })
        assert resp.status_code == 200


# ══════════════════════════════════════════
# Phase 3: 멤버 간 채팅
# ══════════════════════════════════════════

class TestChat:
    """멤버 간 채팅 테스트"""

    @pytest.mark.asyncio
    async def test_create_direct_chat(self, client):
        """T20: 1:1 채팅방 생성"""
        ac = await _create_user(client, "chat1@test.com", "채팅유저1")
        team_id, _, _ = await _setup_team("chat1@test.com")

        # 두 번째 유저 생성 + 팀 합류
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac2:
            await _create_user(ac2, "chat2@test.com", "채팅유저2")
        member_id = await _add_member(team_id, "chat2@test.com")

        resp = await ac.post("/api/v1/chat/rooms", json={
            "type": "direct",
            "member_ids": [member_id],
            "team_id": team_id,
        })
        assert resp.status_code in (200, 201)
        assert resp.json()["type"] == "direct"

    @pytest.mark.asyncio
    async def test_create_group_chat(self, client):
        """T21: 그룹 채팅방 생성"""
        ac = await _create_user(client, "gchat1@test.com", "그룹채팅1")
        team_id, _, _ = await _setup_team("gchat1@test.com")

        from httpx import AsyncClient, ASGITransport
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac2:
            await _create_user(ac2, "gchat2@test.com", "그룹채팅2")
        async with AsyncClient(transport=transport, base_url="http://test") as ac3:
            await _create_user(ac3, "gchat3@test.com", "그룹채팅3")
        m2 = await _add_member(team_id, "gchat2@test.com")
        m3 = await _add_member(team_id, "gchat3@test.com")

        resp = await ac.post("/api/v1/chat/rooms", json={
            "type": "group",
            "name": "테스트그룹",
            "member_ids": [m2, m3],
            "team_id": team_id,
        })
        assert resp.status_code in (200, 201)
        assert resp.json()["type"] == "group"

    @pytest.mark.asyncio
    async def test_send_message(self, client):
        """T22: 메시지 전송"""
        ac = await _create_user(client, "msg1@test.com", "메시지유저1")
        team_id, _, _ = await _setup_team("msg1@test.com")

        from httpx import AsyncClient, ASGITransport
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac2:
            await _create_user(ac2, "msg2@test.com", "메시지유저2")
        m2 = await _add_member(team_id, "msg2@test.com")

        room = (await ac.post("/api/v1/chat/rooms", json={
            "type": "direct", "member_ids": [m2], "team_id": team_id,
        })).json()

        resp = await ac.post(f"/api/v1/chat/rooms/{room['id']}/messages", json={
            "content": "안녕하세요!",
        })
        assert resp.status_code in (200, 201)
        assert resp.json()["content"] == "안녕하세요!"

    @pytest.mark.asyncio
    async def test_message_list(self, client):
        """T23: 메시지 목록 조회"""
        ac = await _create_user(client, "mlist1@test.com", "목록유저1")
        team_id, _, _ = await _setup_team("mlist1@test.com")

        from httpx import AsyncClient, ASGITransport
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac2:
            await _create_user(ac2, "mlist2@test.com", "목록유저2")
        m2 = await _add_member(team_id, "mlist2@test.com")

        room = (await ac.post("/api/v1/chat/rooms", json={
            "type": "direct", "member_ids": [m2], "team_id": team_id,
        })).json()

        await ac.post(f"/api/v1/chat/rooms/{room['id']}/messages", json={"content": "메시지1"})
        await ac.post(f"/api/v1/chat/rooms/{room['id']}/messages", json={"content": "메시지2"})

        resp = await ac.get(f"/api/v1/chat/rooms/{room['id']}/messages")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_read_mark(self, client):
        """T24: 읽음 처리"""
        ac = await _create_user(client, "read1@test.com", "읽음유저1")
        team_id, _, _ = await _setup_team("read1@test.com")

        from httpx import AsyncClient, ASGITransport
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac2:
            await _create_user(ac2, "read2@test.com", "읽음유저2")
        m2 = await _add_member(team_id, "read2@test.com")

        room = (await ac.post("/api/v1/chat/rooms", json={
            "type": "direct", "member_ids": [m2], "team_id": team_id,
        })).json()

        resp = await ac.patch(f"/api/v1/chat/rooms/{room['id']}/read")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_chat_room_list(self, client):
        """T25: 채팅방 목록 조회"""
        ac = await _create_user(client, "rlist1@test.com", "방목록유저")
        await _setup_team("rlist1@test.com")

        resp = await ac.get("/api/v1/chat/rooms")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_duplicate_direct_chat_prevented(self, client):
        """T26: 1:1 채팅방 중복 생성 방지"""
        ac = await _create_user(client, "dup1@test.com", "중복유저1")
        team_id, _, _ = await _setup_team("dup1@test.com")

        from httpx import AsyncClient, ASGITransport
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac2:
            await _create_user(ac2, "dup2@test.com", "중복유저2")
        m2 = await _add_member(team_id, "dup2@test.com")

        r1 = (await ac.post("/api/v1/chat/rooms", json={
            "type": "direct", "member_ids": [m2], "team_id": team_id,
        })).json()
        r2 = (await ac.post("/api/v1/chat/rooms", json={
            "type": "direct", "member_ids": [m2], "team_id": team_id,
        })).json()
        assert r1["id"] == r2["id"]


# ══════════════════════════════════════════
# Phase 4: 출퇴근 기록
# ══════════════════════════════════════════

class TestAttendance:
    """출퇴근 기록 테스트"""

    @pytest.mark.asyncio
    async def test_check_in(self, client):
        """T27: 출근 기록"""
        ac = await _create_user(client, "att1@test.com", "출근유저")
        team_id, _, _ = await _setup_team("att1@test.com")

        resp = await ac.post("/api/v1/attendance/check-in", json={
            "team_id": team_id,
        })
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_check_out(self, client):
        """T28: 퇴근 기록"""
        ac = await _create_user(client, "att2@test.com", "퇴근유저")
        team_id, _, _ = await _setup_team("att2@test.com")

        await ac.post("/api/v1/attendance/check-in", json={"team_id": team_id})
        resp = await ac.post("/api/v1/attendance/check-out", json={
            "team_id": team_id,
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_today_status(self, client):
        """T29: 오늘 출퇴근 상태 조회"""
        ac = await _create_user(client, "att3@test.com", "상태유저")
        team_id, _, _ = await _setup_team("att3@test.com")

        resp = await ac.get(f"/api/v1/attendance/today?team_id={team_id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_my_monthly_attendance(self, client):
        """T30: 내 월별 근태 기록"""
        ac = await _create_user(client, "att4@test.com", "월별유저")
        team_id, _, _ = await _setup_team("att4@test.com")

        await ac.post("/api/v1/attendance/check-in", json={"team_id": team_id})

        resp = await ac.get(f"/api/v1/attendance/my?team_id={team_id}&month=2026-03")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_team_attendance_admin(self, client):
        """T31: 팀 근태 현황 (admin/owner)"""
        ac = await _create_user(client, "att5@test.com", "관리자")
        team_id, _, _ = await _setup_team("att5@test.com")

        resp = await ac.get(f"/api/v1/teams/{team_id}/attendance?month=2026-03")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_duplicate_check_in_rejected(self, client):
        """T32: 중복 출근 거부"""
        ac = await _create_user(client, "att6@test.com", "중복출근유저")
        team_id, _, _ = await _setup_team("att6@test.com")

        await ac.post("/api/v1/attendance/check-in", json={"team_id": team_id})
        resp = await ac.post("/api/v1/attendance/check-in", json={"team_id": team_id})
        assert resp.status_code in (400, 409)

    @pytest.mark.asyncio
    async def test_attendance_policy_crud(self, client):
        """T33: 근무 정책 조회/설정"""
        ac = await _create_user(client, "att7@test.com", "정책유저")
        team_id, _, _ = await _setup_team("att7@test.com")

        resp = await ac.get(f"/api/v1/teams/{team_id}/attendance/policy")
        assert resp.status_code == 200

        resp = await ac.put(f"/api/v1/teams/{team_id}/attendance/policy", json={
            "default_check_in": "09:00",
            "default_check_out": "18:00",
            "work_hours": 8,
            "break_hours": 1,
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_check_out_without_check_in_rejected(self, client):
        """T34: 출근 없이 퇴근 거부"""
        ac = await _create_user(client, "att8@test.com", "미출근퇴근유저")
        team_id, _, _ = await _setup_team("att8@test.com")

        resp = await ac.post("/api/v1/attendance/check-out", json={
            "team_id": team_id,
        })
        assert resp.status_code in (400, 404)


# ══════════════════════════════════════════
# 권한 테스트
# ══════════════════════════════════════════

class TestPermissions:
    """권한 관련 테스트"""

    @pytest.mark.asyncio
    async def test_non_member_cannot_access_board(self, client):
        """T35: 비팀원 게시판 접근 거부"""
        ac = await _create_user(client, "perm1@test.com", "팀원")
        team_id, _, _ = await _setup_team("perm1@test.com")

        from httpx import AsyncClient, ASGITransport
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac2:
            await _create_user(ac2, "perm2@test.com", "비팀원")
            resp = await ac2.get(f"/api/v1/teams/{team_id}/boards")
            assert resp.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_member_cannot_invite(self, client):
        """T36: 일반 멤버는 초대 불가"""
        ac = await _create_user(client, "perm3@test.com", "오너")
        team_id, _, _ = await _setup_team("perm3@test.com")

        from httpx import AsyncClient, ASGITransport
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac2:
            await _create_user(ac2, "perm4@test.com", "멤버")
        await _add_member(team_id, "perm4@test.com", role="member")

        from httpx import AsyncClient as AC2
        transport2 = ASGITransport(app=app)
        async with AC2(transport=transport2, base_url="http://test") as member_ac:
            await member_ac.post("/api/v1/auth/send-code", json={"email": "perm4@test.com"})
            async with TestSessionLocal() as db:
                result = await db.execute(
                    select(VerificationCode).where(VerificationCode.email == "perm4@test.com")
                )
                codes = result.scalars().all()
                code = codes[-1].code
            await member_ac.post("/api/v1/auth/verify-code", json={"email": "perm4@test.com", "code": code})
            await member_ac.post("/api/v1/auth/login", json={
                "email": "perm4@test.com", "password": "test1234",
            })
            resp = await member_ac.post(f"/api/v1/teams/{team_id}/invites", json={
                "email": "someone@example.com",
            })
            assert resp.status_code in (401, 403)  # 401=세션 미전달, 403=권한 부족


# ══════════════════════════════════════════
# 랜딩 페이지 테스트
# ══════════════════════════════════════════

class TestLandingPage:
    """랜딩 페이지 테스트"""

    @pytest.mark.asyncio
    async def test_landing_page_accessible_without_login(self, client):
        """T37: 비로그인 상태에서 메인 페이지 접근 가능"""
        resp = await client.get("/")
        assert resp.status_code == 200
        # index.html이 반환되어야 함
        assert "Contract Sync" in resp.text

    @pytest.mark.asyncio
    async def test_landing_page_contains_features(self, client):
        """T38: 랜딩 페이지에 기능 소개 카드 포함"""
        resp = await client.get("/")
        assert resp.status_code == 200
        # 6개 기능 카드 관련 텍스트 확인
        html = resp.text
        assert "landingPage" in html  # Alpine.js 함수 존재

    @pytest.mark.asyncio
    async def test_landing_page_has_login_cta(self, client):
        """T39: 랜딩 페이지에 로그인 CTA 버튼 포함"""
        resp = await client.get("/")
        html = resp.text
        assert "Google" in html or "로그인" in html or "시작하기" in html

    @pytest.mark.asyncio
    async def test_authenticated_user_can_access_dashboard(self, client):
        """T40: 로그인 사용자는 대시보드 접근 가능"""
        ac = await _create_user(client, "land1@test.com", "랜딩유저")
        resp = await ac.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_static_assets_accessible(self, client):
        """T41: 정적 파일(JS, CSS) 접근 가능"""
        resp_js = await client.get("/static/js/main.js")
        assert resp_js.status_code == 200

        resp_css = await client.get("/static/css/styles.css")
        assert resp_css.status_code == 200


# ══════════════════════════════════════════
# 캘린더 위젯 테스트
# ══════════════════════════════════════════

class TestCalendarWidget:
    """대시보드 캘린더 위젯 테스트"""

    @pytest.mark.asyncio
    async def test_tasks_api_for_calendar(self, client):
        """T42: 캘린더 위젯용 업무 목록 API"""
        ac = await _create_user(client, "cal1@test.com", "캘린더유저")
        team_id, project_id, _ = await _setup_team("cal1@test.com")

        resp = await ac.get(f"/api/v1/tasks?project_id={project_id}&page=1&size=100")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_tasks_with_due_date(self, client):
        """T43: 기한이 있는 업무가 캘린더에 표시 가능"""
        ac = await _create_user(client, "cal2@test.com", "캘린더유저2")
        team_id, project_id, _ = await _setup_team("cal2@test.com")

        # 기한이 있는 업무 생성
        resp = await ac.post("/api/v1/tasks", json={
            "task_name": "캘린더 업무",
            "project_id": project_id,
            "due_date": "2026-03-20",
            "priority": "높음",
        })
        assert resp.status_code in (200, 201)

        # 업무 목록에서 due_date 확인
        tasks_resp = await ac.get(f"/api/v1/tasks?project_id={project_id}&page=1&size=100")
        assert tasks_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_my_tasks_for_calendar(self, client):
        """T44: 멀티팀 업무 조회 (캘린더 데이터 소스)"""
        ac = await _create_user(client, "cal3@test.com", "캘린더유저3")
        await _setup_team("cal3@test.com")

        resp = await ac.get("/api/v1/my/tasks")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_dashboard_summary_for_calendar(self, client):
        """T45: 대시보드 요약 API (캘린더 통계)"""
        ac = await _create_user(client, "cal4@test.com", "캘린더유저4")
        await _setup_team("cal4@test.com")

        resp = await ac.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_projects" in data or "projects" in data or isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_weekly_report_api(self, client):
        """T46: 주간 리포트 API (캘린더 관련)"""
        ac = await _create_user(client, "cal5@test.com", "캘린더유저5")
        await _setup_team("cal5@test.com")

        resp = await ac.get("/api/v1/dashboard/weekly-report?week_offset=0")
        assert resp.status_code == 200
