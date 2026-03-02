"""Phase 2: 완료 보고 + 피드백 통합 테스트 (16개)"""
import asyncio
import json
import bcrypt
import httpx
from datetime import datetime, timedelta

BASE = "http://127.0.0.1:8000/api/v1"
EMAIL = "test_phase2@test.com"
PW = "test1234"


async def setup_user_and_data(c: httpx.AsyncClient):
    """API를 통해 테스트 유저 + 프로젝트 + 업무 생성"""
    from app.database import async_session, User, Task
    from sqlalchemy import select

    # 1) 유저 생성 (DB 직접 — 회원가입 API 없음)
    async with async_session() as db:
        existing = await db.execute(select(User).where(User.email == EMAIL))
        user = existing.scalar_one_or_none()
        if not user:
            hashed = bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode()
            user = User(email=EMAIL, password_hash=hashed, name="Phase2 Tester", is_verified=True)
            db.add(user)
            await db.commit()
            await db.refresh(user)
        user_id = user.id

    # 2) 로그인
    r = await c.post("/auth/login/email", json={"email": EMAIL, "password": PW})
    assert r.status_code == 200, f"Login failed: {r.text}"
    cookies = dict(r.cookies)

    # 3) 발주처 생성 (이미 존재하면 조회)
    r = await c.post("/clients", json={
        "name": "테스트 발주처",
        "contact_name": "김담당",
        "contact_email": "client@example.com",
    }, cookies=cookies)
    if r.status_code == 200:
        client_id = r.json()["id"]
    else:
        r2 = await c.get("/clients?page=1&size=100", cookies=cookies)
        clients = r2.json().get("clients", [])
        client_id = next(cl["id"] for cl in clients if cl["name"] == "테스트 발주처")

    # 4) 프로젝트 생성 (API)
    r = await c.post("/projects", json={
        "project_name": "Phase2 테스트 프로젝트",
        "project_type": "outsourcing",
        "client_id": client_id,
    }, cookies=cookies)
    assert r.status_code == 200, f"Project create failed: {r.text}"
    project_id = r.json()["id"]

    # 5) 업무 3건 생성 (API) + DB에서 is_client_facing, status 직접 설정
    task_ids = {}
    for name, cf, status in [
        ("고객대면 업무", True, "completed"),
        ("내부 업무", False, "completed"),
        ("미완료 업무", True, "pending"),
    ]:
        r = await c.post("/tasks", json={
            "task_name": name,
            "project_id": project_id,
            "is_client_facing": cf,
            "priority": "보통",
        }, cookies=cookies)
        assert r.status_code == 200, f"Task create failed ({name}): {r.text}"
        task_ids[name] = r.json()["id"]

    # API로 status 변경이 안 되는 경우 대비 → DB 직접
    async with async_session() as db:
        for name, cf, status in [
            ("고객대면 업무", True, "completed"),
            ("내부 업무", False, "completed"),
            ("미완료 업무", True, "pending"),
        ]:
            task = await db.get(Task, task_ids[name])
            task.is_client_facing = cf
            task.status = status
        await db.commit()

    return {
        "user_id": user_id,
        "project_id": project_id,
        "client_id": client_id,
        "task_cf_id": task_ids["고객대면 업무"],
        "task_noncf_id": task_ids["내부 업무"],
        "task_pending_id": task_ids["미완료 업무"],
        "cookies": cookies,
    }


async def main():
    passed = 0
    failed = 0
    results = []

    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        data = await setup_user_and_data(c)
        cookies = data["cookies"]

        # ═══ 완료 보고 테스트 ═══

        # T1: 정상 생성 (즉시 발송)
        r = await c.post(f"/tasks/{data['task_cf_id']}/completion-report", json={
            "recipient_email": "client@example.com",
            "subject": "[테스트] 업무 완료 안내",
            "body_html": "<p>업무가 완료되었습니다.</p>",
        }, cookies=cookies)
        if r.status_code == 200:
            rdata = r.json()
            has_token = bool(rdata.get("feedback_token"))
            is_sent = rdata.get("status") == "sent"
            if has_token and is_sent:
                results.append(("T1 정상 생성 (즉시)", "PASS", f"token={rdata['feedback_token'][:16]}..."))
                passed += 1
                report_id = rdata["id"]
                feedback_token = rdata["feedback_token"]
            else:
                results.append(("T1 정상 생성", "FAIL", f"token={has_token}, status={rdata.get('status')}"))
                failed += 1
                report_id = None
                feedback_token = None
        else:
            results.append(("T1 정상 생성", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
            failed += 1
            report_id = None
            feedback_token = None

        # task 상태 확인 (report_sent)
        r2 = await c.get(f"/tasks/{data['task_cf_id']}", cookies=cookies)
        if r2.status_code == 200 and r2.json().get("status") == "report_sent":
            results.append(("T1b task→report_sent", "PASS", ""))
            passed += 1
        else:
            results.append(("T1b task→report_sent", "FAIL", f"status={r2.json().get('status') if r2.status_code==200 else r2.status_code}"))
            failed += 1

        # T2: 비고객대면 업무 → 400
        r = await c.post(f"/tasks/{data['task_noncf_id']}/completion-report", json={
            "recipient_email": "x@x.com",
            "subject": "test",
            "body_html": "<p>test</p>",
        }, cookies=cookies)
        if r.status_code == 400 and "대면" in r.json().get("detail", ""):
            results.append(("T2 비고객대면 → 400", "PASS", r.json()["detail"]))
            passed += 1
        else:
            results.append(("T2 비고객대면 → 400", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T3: 미완료 업무 → 400
        r = await c.post(f"/tasks/{data['task_pending_id']}/completion-report", json={
            "recipient_email": "x@x.com",
            "subject": "test",
            "body_html": "<p>test</p>",
        }, cookies=cookies)
        if r.status_code == 400 and "완료된" in r.json().get("detail", ""):
            results.append(("T3 미완료 업무 → 400", "PASS", r.json()["detail"]))
            passed += 1
        else:
            results.append(("T3 미완료 업무 → 400", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
            failed += 1

        # T4: 중복 생성 → 409
        r = await c.post(f"/tasks/{data['task_cf_id']}/completion-report", json={
            "recipient_email": "x@x.com",
            "subject": "dup",
            "body_html": "<p>dup</p>",
        }, cookies=cookies)
        if r.status_code == 409:
            results.append(("T4 중복 생성 → 409", "PASS", r.json().get("detail", "")))
            passed += 1
        else:
            results.append(("T4 중복 생성 → 409", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T5: 조회
        if report_id:
            r = await c.get(f"/tasks/{data['task_cf_id']}/completion-report", cookies=cookies)
            if r.status_code == 200 and r.json().get("id") == report_id:
                results.append(("T5 보고 조회", "PASS", f"id={report_id}"))
                passed += 1
            else:
                results.append(("T5 보고 조회", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T5 보고 조회", "SKIP", "T1 실패"))

        # T6: 발송된 보고 수정 → 400
        if report_id:
            r = await c.put(f"/completion-reports/{report_id}", json={
                "subject": "수정 시도"
            }, cookies=cookies)
            if r.status_code == 400 and "예약" in r.json().get("detail", ""):
                results.append(("T6 발송 보고 수정 → 400", "PASS", r.json()["detail"]))
                passed += 1
            else:
                results.append(("T6 발송 보고 수정 → 400", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T6 발송 보고 수정 → 400", "SKIP", "T1 실패"))

        # T7: 재발송
        if report_id:
            r = await c.post(f"/completion-reports/{report_id}/resend", cookies=cookies)
            if r.status_code == 200:
                new_token = r.json().get("feedback_token")
                token_changed = new_token != feedback_token
                if token_changed:
                    results.append(("T7 재발송 + 토큰 갱신", "PASS", f"new_token={new_token[:16]}..."))
                    passed += 1
                    feedback_token = new_token  # 갱신된 토큰 사용
                else:
                    results.append(("T7 재발송", "FAIL", "토큰 미변경"))
                    failed += 1
            else:
                results.append(("T7 재발송", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
                failed += 1
        else:
            results.append(("T7 재발송", "SKIP", "T1 실패"))

        # ═══ 예약 보고 테스트 ═══

        # 새 업무 생성 (예약 테스트용) — API + DB 보정
        r = await c.post("/tasks", json={
            "task_name": "예약 테스트 업무",
            "project_id": data["project_id"],
            "is_client_facing": True,
            "priority": "보통",
        }, cookies=cookies)
        assert r.status_code == 200, f"Sched task create failed: {r.text}"
        sched_task_id = r.json()["id"]

        from app.database import async_session, Task
        async with async_session() as db:
            sched_task = await db.get(Task, sched_task_id)
            sched_task.is_client_facing = True
            sched_task.status = "completed"
            await db.commit()

        scheduled_time = (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"
        r = await c.post(f"/tasks/{sched_task_id}/completion-report", json={
            "recipient_email": "client@example.com",
            "subject": "예약 보고",
            "body_html": "<p>예약</p>",
            "scheduled_at": scheduled_time,
        }, cookies=cookies)
        if r.status_code == 200 and r.json().get("status") == "scheduled":
            results.append(("T8 예약 생성", "PASS", f"scheduled_at={r.json().get('scheduled_at')}"))
            passed += 1
            sched_report_id = r.json()["id"]
        else:
            results.append(("T8 예약 생성", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
            failed += 1
            sched_report_id = None

        # T9: 예약 보고 수정
        if sched_report_id:
            r = await c.put(f"/completion-reports/{sched_report_id}", json={
                "subject": "수정된 예약 보고"
            }, cookies=cookies)
            if r.status_code == 200 and r.json().get("subject") == "수정된 예약 보고":
                results.append(("T9 예약 보고 수정", "PASS", ""))
                passed += 1
            else:
                results.append(("T9 예약 보고 수정", "FAIL", f"status={r.status_code}"))
                failed += 1

            # T10: 예약 보고 삭제 + task→completed 복원
            r = await c.delete(f"/completion-reports/{sched_report_id}", cookies=cookies)
            if r.status_code == 200:
                r2 = await c.get(f"/tasks/{sched_task_id}", cookies=cookies)
                task_restored = r2.status_code == 200 and r2.json().get("status") == "completed"
                if task_restored:
                    results.append(("T10 예약 삭제 + task복원", "PASS", ""))
                    passed += 1
                else:
                    results.append(("T10 예약 삭제", "FAIL", f"task.status={r2.json().get('status')}"))
                    failed += 1
            else:
                results.append(("T10 예약 삭제", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T9 예약 보고 수정", "SKIP", "T8 실패"))
            results.append(("T10 예약 삭제", "SKIP", "T8 실패"))

        # ═══ 피드백 테스트 ═══

        # T11: 토큰으로 정보 조회
        if feedback_token:
            r = await c.get(f"/feedback/{feedback_token}")
            if r.status_code == 200 and r.json().get("task_name") == "고객대면 업무":
                results.append(("T11 피드백 정보 조회", "PASS", f"task_name={r.json()['task_name']}"))
                passed += 1
            else:
                results.append(("T11 피드백 정보 조회", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
                failed += 1
        else:
            results.append(("T11 피드백 정보 조회", "SKIP", "토큰 없음"))

        # T12: 만료 토큰 → 410
        # 만료 테스트용 업무 + 보고 생성 (API + DB)
        r = await c.post("/tasks", json={
            "task_name": "만료 테스트",
            "project_id": data["project_id"],
            "is_client_facing": True,
            "priority": "보통",
        }, cookies=cookies)
        assert r.status_code == 200, f"Exp task create failed: {r.text}"
        exp_task_id = r.json()["id"]

        from app.database import CompletionReport, utc_now as db_utc_now
        import secrets
        expired_token = secrets.token_urlsafe(48)
        async with async_session() as db:
            exp_task = await db.get(Task, exp_task_id)
            exp_task.is_client_facing = True
            exp_task.status = "completed"

            exp_report = CompletionReport(
                task_id=exp_task_id, project_id=data["project_id"],
                sender_id=data["user_id"],
                recipient_email="x@x.com", subject="expired",
                body_html="<p>e</p>",
                feedback_token=expired_token,
                feedback_token_expires_at=db_utc_now() - timedelta(days=1),
                status="sent",
            )
            db.add(exp_report)
            await db.commit()

        r = await c.get(f"/feedback/{expired_token}")
        if r.status_code == 410:
            results.append(("T12 만료 토큰 → 410", "PASS", r.json().get("detail", "")))
            passed += 1
        else:
            results.append(("T12 만료 토큰 → 410", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T13: confirmed 제출
        if feedback_token:
            r = await c.post(f"/feedback/{feedback_token}", json={
                "feedback_type": "confirmed",
                "client_name": "김담당",
            })
            if r.status_code == 200 and r.json().get("feedback_type") == "confirmed":
                # task 상태 확인
                r2 = await c.get(f"/tasks/{data['task_cf_id']}", cookies=cookies)
                if r2.status_code == 200 and r2.json().get("status") == "confirmed":
                    results.append(("T13 confirmed → task=confirmed", "PASS", ""))
                    passed += 1
                else:
                    results.append(("T13 confirmed", "FAIL", f"task.status={r2.json().get('status')}"))
                    failed += 1
            else:
                results.append(("T13 confirmed", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
                failed += 1
        else:
            results.append(("T13 confirmed", "SKIP", "토큰 없음"))

        # T14: revision (내용 없음) → 400
        if feedback_token:
            r = await c.post(f"/feedback/{feedback_token}", json={
                "feedback_type": "revision",
            })
            if r.status_code == 400 and "내용" in r.json().get("detail", ""):
                results.append(("T14 revision 내용없음 → 400", "PASS", r.json()["detail"]))
                passed += 1
            else:
                results.append(("T14 revision 내용없음", "FAIL", f"status={r.status_code}"))
                failed += 1

            # T15: revision (내용 있음) → task=revision_requested
            r = await c.post(f"/feedback/{feedback_token}", json={
                "feedback_type": "revision",
                "content": "로고 색상을 변경해주세요",
                "client_name": "김담당",
            })
            if r.status_code == 200:
                r2 = await c.get(f"/tasks/{data['task_cf_id']}", cookies=cookies)
                if r2.status_code == 200 and r2.json().get("status") == "revision_requested":
                    results.append(("T15 revision → task=revision_requested", "PASS", ""))
                    passed += 1
                else:
                    results.append(("T15 revision", "FAIL", f"task.status={r2.json().get('status')}"))
                    failed += 1
            else:
                results.append(("T15 revision", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T14 revision 내용없음", "SKIP", "토큰 없음"))
            results.append(("T15 revision 제출", "SKIP", "토큰 없음"))

        # T16: 피드백 이력 조회
        r = await c.get(f"/tasks/{data['task_cf_id']}/feedbacks", cookies=cookies)
        if r.status_code == 200:
            total = r.json().get("total", 0)
            if total >= 2:  # confirmed + revision
                results.append(("T16 피드백 이력 조회", "PASS", f"total={total}"))
                passed += 1
            else:
                results.append(("T16 피드백 이력", "FAIL", f"total={total}"))
                failed += 1
        else:
            results.append(("T16 피드백 이력", "FAIL", f"status={r.status_code}"))
            failed += 1

    # 결과 출력
    print(f"\n{'='*60}")
    print(f"  Phase 2 통합 테스트 결과: {passed}/{passed+failed}")
    print(f"{'='*60}")
    for name, status, detail in results:
        icon = "✅" if status == "PASS" else ("⏭️" if status == "SKIP" else "❌")
        print(f"  {icon} {name}: {status}")
        if detail:
            print(f"     → {detail}")
    print()

    if failed > 0:
        exit(1)


asyncio.run(main())
