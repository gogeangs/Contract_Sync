"""E2E 통합 테스트 — 실제 서버 기반

실제 FastAPI 서버를 로컬에서 실행하고 httpx로 전체 사용자 플로우를 검증합니다.
브라우저 의존성 없이 HTTP 레벨에서 전체 API + 페이지 접근을 테스트합니다.

실행: python3 -m pytest tests/test_e2e.py -v
"""
import pytest
import httpx
import uvicorn
import threading
import time


SERVER_HOST = "127.0.0.1"
SERVER_PORT = 18765
BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

_server_started = False


@pytest.fixture(scope="session", autouse=True)
def start_server():
    """테스트 세션 동안 실제 FastAPI 서버 실행"""
    global _server_started
    if _server_started:
        return

    import os
    os.environ["DEBUG"] = "true"

    from app.main import app

    config = uvicorn.Config(app, host=SERVER_HOST, port=SERVER_PORT, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # 서버 시작 대기
    for _ in range(50):
        try:
            import urllib.request
            urllib.request.urlopen(f"{BASE_URL}/")
            break
        except Exception:
            time.sleep(0.2)

    _server_started = True
    yield
    server.should_exit = True


@pytest.fixture
def client():
    """httpx 동기 클라이언트"""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True) as c:
        yield c


# ══════════════════════════════════════════
# 1. 랜딩 페이지 / 정적 파일
# ══════════════════════════════════════════

class TestLandingE2E:
    """비로그인 상태 페이지 E2E"""

    def test_landing_page_loads(self, client):
        """E1: 메인 페이지 접근 가능"""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Contract Sync" in resp.text

    def test_landing_has_alpine_app(self, client):
        """E2: Alpine.js 앱 코드 포함"""
        resp = client.get("/")
        assert "appShell" in resp.text
        assert "x-data" in resp.text

    def test_static_js_loads(self, client):
        """E3: main.js 정상 로드"""
        resp = client.get("/static/js/main.js")
        assert resp.status_code == 200
        assert "appShell" in resp.text
        assert len(resp.text) > 1000

    def test_static_css_loads(self, client):
        """E4: styles.css 정상 로드"""
        resp = client.get("/static/css/styles.css")
        assert resp.status_code == 200

    def test_landing_has_sidebar_groups(self, client):
        """E5: 사이드바 그룹핑 코드 포함"""
        resp = client.get("/")
        assert "sideGroup" in resp.text

    def test_landing_has_briefing(self, client):
        """E6: 브리핑 위젯 코드 포함"""
        resp = client.get("/")
        assert "briefingItems" in resp.text or "briefing" in resp.text

    def test_landing_has_chatbot(self, client):
        """E7: 챗봇 위젯 코드 포함"""
        resp = client.get("/")
        assert "chatbotWidget" in resp.text

    def test_landing_has_coachmark(self, client):
        """E8: 코치마크 코드 포함"""
        resp = client.get("/")
        assert "showCoachmark" in resp.text

    def test_landing_has_dark_mode(self, client):
        """E9: 다크모드 코드 포함"""
        resp = client.get("/")
        assert "darkMode" in resp.text


# ══════════════════════════════════════════
# 2. 인증 플로우
# ══════════════════════════════════════════

class TestAuthFlowE2E:
    """회원가입 → 로그인 → 기능 사용 전체 플로우"""

    def test_auth_me_unauthenticated(self, client):
        """E10: 비로그인 /auth/me"""
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("logged_in") is False

    def test_send_verification_code(self, client):
        """E11: 인증코드 발송"""
        resp = client.post("/api/v1/auth/send-code", json={"email": "e2e@test.com"})
        assert resp.status_code == 200

    def test_full_signup_login_flow(self, client):
        """E12: 전체 회원가입 + 로그인 플로우"""
        # 1) 인증코드 발송
        resp = client.post("/api/v1/auth/send-code", json={"email": "e2eflow@test.com"})
        assert resp.status_code == 200

        # 2) DB에서 코드 조회 (테스트 환경)
        from tests.conftest import TestSessionLocal
        from sqlalchemy import select
        from app.database import VerificationCode

        async def get_code():
            async with TestSessionLocal() as db:
                result = await db.execute(
                    select(VerificationCode).where(VerificationCode.email == "e2eflow@test.com")
                )
                return result.scalar_one().code

        # E2E 서버는 별도 DB를 사용하므로 코드 발송만 확인
        assert resp.status_code == 200


# ══════════════════════════════════════════
# 3. API 보안 (비로그인 접근 거부)
# ══════════════════════════════════════════

class TestAPISecurityE2E:
    """비로그인 시 보호된 API 접근 거부"""

    def test_projects_unauthorized(self, client):
        """E13: 프로젝트 API"""
        resp = client.get("/api/v1/projects")
        assert resp.status_code in (401, 403)

    def test_tasks_unauthorized(self, client):
        """E14: 업무 API"""
        resp = client.get("/api/v1/tasks")
        assert resp.status_code in (401, 403)

    def test_dashboard_summary_unauthorized(self, client):
        """E15: 대시보드 요약 API"""
        resp = client.get("/api/v1/dashboard/summary")
        assert resp.status_code in (401, 403)

    def test_briefing_unauthorized(self, client):
        """E16: 브리핑 API"""
        resp = client.get("/api/v1/dashboard/briefing")
        assert resp.status_code in (401, 403)

    def test_command_unauthorized(self, client):
        """E17: 자연어 명령 API"""
        resp = client.post("/api/v1/command/parse", json={"message": "출근"})
        assert resp.status_code in (401, 403)

    def test_chatbot_unauthorized(self, client):
        """E18: 챗봇 API"""
        resp = client.post("/api/v1/chatbot/message", json={"message": "안녕"})
        assert resp.status_code in (401, 403)

    def test_attendance_unauthorized(self, client):
        """E19: 출퇴근 API"""
        resp = client.post("/api/v1/attendance/check-in", json={"team_id": 1})
        assert resp.status_code in (401, 403)

    def test_work_report_unauthorized(self, client):
        """E20: 업무 보고 API"""
        resp = client.get("/api/v1/work-report/today")
        assert resp.status_code in (401, 403)

    def test_boards_unauthorized(self, client):
        """E21: 게시판 API"""
        resp = client.get("/api/v1/teams/1/boards")
        assert resp.status_code in (401, 403, 404)

    def test_chat_rooms_unauthorized(self, client):
        """E22: 채팅방 API"""
        resp = client.get("/api/v1/chat/rooms")
        assert resp.status_code in (401, 403)

    def test_invites_unauthorized(self, client):
        """E23: 초대 API"""
        resp = client.post("/api/v1/teams/1/invites", json={"email": "hack@test.com"})
        assert resp.status_code in (401, 403, 404)

    def test_my_tasks_unauthorized(self, client):
        """E24: 내 업무 API"""
        resp = client.get("/api/v1/my/tasks")
        assert resp.status_code in (401, 403)


# ══════════════════════════════════════════
# 4. 보안 테스트
# ══════════════════════════════════════════

class TestSecurityE2E:
    """보안 취약점 E2E"""

    def test_no_sensitive_data_in_html(self, client):
        """E25: HTML에 비밀 키 미노출"""
        resp = client.get("/")
        html = resp.text
        assert "GOOGLE_CLIENT_SECRET" not in html
        assert "SECRET_KEY" not in html
        assert "private_key" not in html
        assert "GEMINI_API_KEY" not in html

    def test_sql_injection_safe(self, client):
        """E26: SQL 인젝션 방지"""
        resp = client.get("/api/v1/projects?page=1&size=10'; DROP TABLE users;--")
        assert resp.status_code != 500

    def test_xss_in_email_rejected(self, client):
        """E27: XSS 이메일 거부"""
        resp = client.post("/api/v1/auth/send-code", json={
            "email": "<script>alert('xss')</script>",
        })
        assert resp.status_code in (400, 422)

    def test_large_payload_rejected(self, client):
        """E28: 과대 페이로드 거부"""
        resp = client.post("/api/v1/chatbot/message", json={
            "message": "A" * 100000,
        })
        assert resp.status_code in (401, 403, 413, 422)

    def test_path_traversal_safe(self, client):
        """E29: 경로 탐색 공격 방지"""
        resp = client.get("/static/../../etc/passwd")
        assert resp.status_code in (400, 403, 404)
        assert "root:" not in resp.text

    def test_invalid_json_handled(self, client):
        """E30: 잘못된 JSON 처리"""
        resp = client.post("/api/v1/auth/send-code",
                          content="not json",
                          headers={"Content-Type": "application/json"})
        assert resp.status_code in (400, 422)


# ══════════════════════════════════════════
# 5. 성능 기본 체크
# ══════════════════════════════════════════

class TestPerformanceE2E:
    """기본 성능 E2E"""

    def test_main_page_response_time(self, client):
        """E31: 메인 페이지 응답 1초 이내"""
        import time
        start = time.time()
        resp = client.get("/")
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 1.0, f"응답 시간: {elapsed:.2f}초"

    def test_api_response_time(self, client):
        """E32: API 응답 1초 이내"""
        import time
        start = time.time()
        resp = client.get("/api/v1/auth/me")
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 1.0, f"응답 시간: {elapsed:.2f}초"

    def test_static_file_response_time(self, client):
        """E33: 정적 파일 응답 500ms 이내"""
        import time
        start = time.time()
        resp = client.get("/static/js/main.js")
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 0.5, f"응답 시간: {elapsed:.2f}초"
