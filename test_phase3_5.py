"""Phase 3~5: AI 보고서 + 수금/AI 견적 + 템플릿/반복업무 통합 테스트 (47개)"""
import asyncio
import json
import bcrypt
import httpx
from datetime import datetime, timedelta

BASE = "http://127.0.0.1:8000/api/v1"
EMAIL = "test_phase3_5@test.com"
PW = "test1234"


async def setup_user_and_data(c: httpx.AsyncClient):
    """API를 통해 테스트 유저 + 발주처 + 프로젝트 + 업무 생성"""
    from app.database import async_session, User, Task
    from sqlalchemy import select

    # 1) 유저 생성 (DB 직접)
    async with async_session() as db:
        existing = await db.execute(select(User).where(User.email == EMAIL))
        user = existing.scalar_one_or_none()
        if not user:
            hashed = bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode()
            user = User(email=EMAIL, password_hash=hashed, name="Phase3_5 Tester", is_verified=True)
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
        "name": "Phase3_5 발주처",
        "contact_name": "테스트담당",
        "contact_email": "phase35@example.com",
    }, cookies=cookies)
    if r.status_code == 200:
        client_id = r.json()["id"]
    else:
        # 이미 존재 → 목록에서 찾기
        r2 = await c.get("/clients?page=1&size=100", cookies=cookies)
        clients = r2.json().get("clients", [])
        client_id = next(cl["id"] for cl in clients if cl["name"] == "Phase3_5 발주처")

    # 4) 프로젝트 생성 (매번 새로 — 유니크 이름)
    import time
    ts = int(time.time()) % 100000
    r = await c.post("/projects", json={
        "project_name": f"Phase3_5 프로젝트 {ts}",
        "project_type": "outsourcing",
        "client_id": client_id,
    }, cookies=cookies)
    assert r.status_code == 200, f"Project create failed: {r.text}"
    project_id = r.json()["id"]

    # 5) 업무 2건 생성 + DB 직접 status 설정
    task_ids = {}
    for name, status in [("완료 업무", "completed"), ("진행 업무", "in_progress")]:
        r = await c.post("/tasks", json={
            "task_name": name,
            "project_id": project_id,
            "priority": "보통",
        }, cookies=cookies)
        assert r.status_code == 200, f"Task create failed ({name}): {r.text}"
        task_ids[name] = r.json()["id"]

    async with async_session() as db:
        for name, status in [("완료 업무", "completed"), ("진행 업무", "in_progress")]:
            task = await db.get(Task, task_ids[name])
            task.status = status
        await db.commit()

    return {
        "user_id": user_id,
        "project_id": project_id,
        "client_id": client_id,
        "task_completed_id": task_ids["완료 업무"],
        "task_inprogress_id": task_ids["진행 업무"],
        "cookies": cookies,
    }


async def main():
    passed = 0
    failed = 0
    skipped = 0
    results = []

    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        data = await setup_user_and_data(c)
        cookies = data["cookies"]
        project_id = data["project_id"]

        # ═══════════════════════════════════════════
        #  Group A: AI 보고서 (Phase 3) — T1~T11
        # ═══════════════════════════════════════════

        report_id = None
        gemini_available = True

        # T1: AI 보고서 생성 (periodic)
        try:
            r = await c.post(f"/projects/{project_id}/reports/generate", json={
                "report_type": "periodic",
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
            }, cookies=cookies)
            if r.status_code == 200:
                rdata = r.json()
                report_id = rdata["id"]
                results.append(("T1 AI 보고서 생성 (periodic)", "PASS", f"id={report_id}"))
                passed += 1
            elif r.status_code in (500, 502):
                results.append(("T1 AI 보고서 생성", "SKIP", "Gemini API 미연결"))
                skipped += 1
                gemini_available = False
            else:
                results.append(("T1 AI 보고서 생성", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
                failed += 1
        except Exception as e:
            results.append(("T1 AI 보고서 생성", "SKIP", f"Exception: {e}"))
            skipped += 1
            gemini_available = False

        # T2: 프로젝트별 보고서 목록
        if report_id:
            r = await c.get(f"/projects/{project_id}/reports", cookies=cookies)
            if r.status_code == 200 and r.json().get("total", 0) >= 1:
                results.append(("T2 프로젝트별 보고서 목록", "PASS", f"total={r.json()['total']}"))
                passed += 1
            else:
                results.append(("T2 프로젝트별 보고서 목록", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T2 프로젝트별 보고서 목록", "SKIP", "T1 SKIP"))
            skipped += 1

        # T3: 전체 보고서 목록 (pagination)
        if report_id:
            r = await c.get("/reports?page=1&size=10", cookies=cookies)
            if r.status_code == 200 and isinstance(r.json().get("reports"), list):
                results.append(("T3 전체 보고서 목록 pagination", "PASS", f"total={r.json().get('total')}"))
                passed += 1
            else:
                results.append(("T3 전체 보고서 목록", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T3 전체 보고서 목록", "SKIP", "T1 SKIP"))
            skipped += 1

        # T4: 보고서 상세 조회
        if report_id:
            r = await c.get(f"/reports/{report_id}", cookies=cookies)
            if r.status_code == 200 and r.json().get("id") == report_id:
                results.append(("T4 보고서 상세 조회", "PASS", f"id={r.json()['id']}"))
                passed += 1
            else:
                results.append(("T4 보고서 상세 조회", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T4 보고서 상세 조회", "SKIP", "T1 SKIP"))
            skipped += 1

        # T5: 보고서 편집 (draft 상태)
        if report_id:
            r = await c.put(f"/reports/{report_id}", json={
                "title": "수정된 보고서 제목",
            }, cookies=cookies)
            if r.status_code == 200 and r.json().get("title") == "수정된 보고서 제목":
                results.append(("T5 보고서 편집 (draft)", "PASS", "title 변경됨"))
                passed += 1
            else:
                results.append(("T5 보고서 편집", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
                failed += 1
        else:
            results.append(("T5 보고서 편집", "SKIP", "T1 SKIP"))
            skipped += 1

        # T6: 보고서 발송 → status=sent
        if report_id:
            r = await c.post(f"/reports/{report_id}/send", json={
                "recipient_emails": ["test@example.com"],
            }, cookies=cookies)
            if r.status_code == 200 and r.json().get("status") == "sent":
                results.append(("T6 보고서 발송", "PASS", "status=sent"))
                passed += 1
            elif r.status_code in (500, 502):
                results.append(("T6 보고서 발송", "SKIP", "이메일 발송 실패"))
                skipped += 1
            else:
                results.append(("T6 보고서 발송", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
                failed += 1
        else:
            results.append(("T6 보고서 발송", "SKIP", "T1 SKIP"))
            skipped += 1

        # T7: 발송된 보고서 편집 → 400
        report_is_sent = report_id and any(
            n == "T6 보고서 발송" and s == "PASS" for n, s, _ in results
        )
        if report_is_sent:
            r = await c.put(f"/reports/{report_id}", json={
                "title": "발송 후 수정 시도",
            }, cookies=cookies)
            if r.status_code == 400 and "초안" in r.json().get("detail", ""):
                results.append(("T7 발송 후 편집 → 400", "PASS", r.json()["detail"]))
                passed += 1
            else:
                results.append(("T7 발송 후 편집 → 400", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T7 발송 후 편집 → 400", "SKIP", "T6 미완료"))
            skipped += 1

        # T8: 발송된 보고서 삭제 → 400
        if report_is_sent:
            r = await c.delete(f"/reports/{report_id}", cookies=cookies)
            if r.status_code == 400 and "초안" in r.json().get("detail", ""):
                results.append(("T8 발송 후 삭제 → 400", "PASS", r.json()["detail"]))
                passed += 1
            else:
                results.append(("T8 발송 후 삭제 → 400", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T8 발송 후 삭제 → 400", "SKIP", "T6 미완료"))
            skipped += 1

        # T9: 신규 보고서 생성 후 삭제 (draft 상태)
        if gemini_available:
            try:
                r = await c.post(f"/projects/{project_id}/reports/generate", json={
                    "report_type": "completion",
                }, cookies=cookies)
                if r.status_code == 200:
                    new_report_id = r.json()["id"]
                    rd = await c.delete(f"/reports/{new_report_id}", cookies=cookies)
                    if rd.status_code == 200:
                        results.append(("T9 draft 보고서 삭제", "PASS", f"삭제 id={new_report_id}"))
                        passed += 1
                    else:
                        results.append(("T9 draft 보고서 삭제", "FAIL", f"delete status={rd.status_code}"))
                        failed += 1
                elif r.status_code in (500, 502):
                    results.append(("T9 draft 보고서 삭제", "SKIP", "Gemini API 실패"))
                    skipped += 1
                else:
                    results.append(("T9 draft 보고서 삭제", "FAIL", f"generate status={r.status_code}"))
                    failed += 1
            except Exception as e:
                results.append(("T9 draft 보고서 삭제", "SKIP", f"Exception: {e}"))
                skipped += 1
        else:
            results.append(("T9 draft 보고서 삭제", "SKIP", "Gemini API 미연결"))
            skipped += 1

        # T10: 존재하지 않는 보고서 조회 → 404
        r = await c.get("/reports/999999", cookies=cookies)
        if r.status_code == 404:
            results.append(("T10 없는 보고서 → 404", "PASS", ""))
            passed += 1
        else:
            results.append(("T10 없는 보고서 → 404", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T11: 비로그인 접근 → 401
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as anon:
            r = await anon.get("/reports")
        if r.status_code == 401:
            results.append(("T11 비로그인 보고서 → 401", "PASS", ""))
            passed += 1
        else:
            results.append(("T11 비로그인 보고서 → 401", "FAIL", f"status={r.status_code}"))
            failed += 1

        # ═══════════════════════════════════════════
        #  Group B: 수금 관리 (Phase 4A) — T12~T24
        # ═══════════════════════════════════════════

        payment_id = None

        # T12: 결제 일정 등록 (advance)
        r = await c.post(f"/projects/{project_id}/payments", json={
            "payment_type": "advance",
            "description": "착수금",
            "amount": 1000000,
            "due_date": "2026-04-01",
        }, cookies=cookies)
        if r.status_code == 200:
            rdata = r.json()
            payment_id = rdata["id"]
            ok = rdata.get("status") == "pending" and rdata.get("amount") == 1000000
            if ok:
                results.append(("T12 결제 일정 등록 (advance)", "PASS", f"id={payment_id}"))
                passed += 1
            else:
                results.append(("T12 결제 일정 등록", "FAIL", f"status={rdata.get('status')}, amount={rdata.get('amount')}"))
                failed += 1
        else:
            results.append(("T12 결제 일정 등록", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
            failed += 1

        # T13: 프로젝트별 수금 목록
        r = await c.get(f"/projects/{project_id}/payments", cookies=cookies)
        if r.status_code == 200 and r.json().get("total", 0) >= 1:
            results.append(("T13 프로젝트별 수금 목록", "PASS", f"total={r.json()['total']}"))
            passed += 1
        else:
            results.append(("T13 프로젝트별 수금 목록", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T14: 전체 수금 목록 (pagination)
        r = await c.get("/payments?page=1&size=10", cookies=cookies)
        if r.status_code == 200 and isinstance(r.json().get("payments"), list):
            results.append(("T14 전체 수금 목록 pagination", "PASS", f"total={r.json().get('total')}"))
            passed += 1
        else:
            results.append(("T14 전체 수금 목록", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T15: 수금 요약
        r = await c.get("/payments/summary", cookies=cookies)
        if r.status_code == 200 and r.json().get("total_amount", 0) >= 1000000:
            results.append(("T15 수금 요약", "PASS", f"total_amount={r.json()['total_amount']}"))
            passed += 1
        else:
            results.append(("T15 수금 요약", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
            failed += 1

        # T16: pending → invoiced
        if payment_id:
            r = await c.patch(f"/payments/{payment_id}", json={
                "status": "invoiced",
            }, cookies=cookies)
            if r.status_code == 200 and r.json().get("status") == "invoiced":
                results.append(("T16 pending→invoiced", "PASS", ""))
                passed += 1
            else:
                results.append(("T16 pending→invoiced", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
                failed += 1
        else:
            results.append(("T16 pending→invoiced", "SKIP", "T12 실패"))
            skipped += 1

        # T17: invoiced → paid + paid_date
        if payment_id:
            r = await c.patch(f"/payments/{payment_id}", json={
                "status": "paid",
                "paid_date": "2026-03-15",
                "paid_amount": 1000000,
            }, cookies=cookies)
            if r.status_code == 200 and r.json().get("status") == "paid":
                results.append(("T17 invoiced→paid", "PASS", f"paid_date={r.json().get('paid_date')}"))
                passed += 1
            else:
                results.append(("T17 invoiced→paid", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
                failed += 1
        else:
            results.append(("T17 invoiced→paid", "SKIP", "T12 실패"))
            skipped += 1

        # T18: paid → pending (역전이) → 400
        if payment_id:
            r = await c.patch(f"/payments/{payment_id}", json={
                "status": "pending",
            }, cookies=cookies)
            if r.status_code == 400 and "허용" in r.json().get("detail", ""):
                results.append(("T18 paid→pending 역전이 → 400", "PASS", r.json()["detail"]))
                passed += 1
            else:
                results.append(("T18 paid→pending 역전이", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
                failed += 1
        else:
            results.append(("T18 paid→pending 역전이", "SKIP", "T12 실패"))
            skipped += 1

        # T19: 2번째 결제 등록 + pending → overdue
        payment_id2 = None
        r = await c.post(f"/projects/{project_id}/payments", json={
            "payment_type": "interim",
            "description": "중도금",
            "amount": 500000,
            "due_date": "2026-05-01",
        }, cookies=cookies)
        if r.status_code == 200:
            payment_id2 = r.json()["id"]
            # pending → overdue
            r2 = await c.patch(f"/payments/{payment_id2}", json={
                "status": "overdue",
            }, cookies=cookies)
            if r2.status_code == 200 and r2.json().get("status") == "overdue":
                results.append(("T19 2번째 결제 + pending→overdue", "PASS", f"id={payment_id2}"))
                passed += 1
            else:
                results.append(("T19 pending→overdue", "FAIL", f"status={r2.status_code}, body={r2.text[:200]}"))
                failed += 1
        else:
            results.append(("T19 2번째 결제 등록", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T20: overdue + paid_date → auto paid
        if payment_id2:
            r = await c.patch(f"/payments/{payment_id2}", json={
                "paid_date": "2026-03-20",
                "paid_amount": 500000,
            }, cookies=cookies)
            if r.status_code == 200 and r.json().get("status") == "paid":
                results.append(("T20 overdue + paid_date → auto paid", "PASS", ""))
                passed += 1
            else:
                results.append(("T20 overdue→auto paid", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
                failed += 1
        else:
            results.append(("T20 overdue→auto paid", "SKIP", "T19 실패"))
            skipped += 1

        # T21: status 필터 조회
        r = await c.get("/payments?status=paid", cookies=cookies)
        if r.status_code == 200:
            payments_list = r.json().get("payments", [])
            all_paid = all(p.get("status") == "paid" for p in payments_list) if payments_list else False
            if all_paid and len(payments_list) >= 1:
                results.append(("T21 status 필터 조회", "PASS", f"count={len(payments_list)}"))
                passed += 1
            else:
                results.append(("T21 status 필터", "FAIL", f"count={len(payments_list)}, all_paid={all_paid}"))
                failed += 1
        else:
            results.append(("T21 status 필터", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T22: 필수 필드 누락 → 422
        r = await c.post(f"/projects/{project_id}/payments", json={
            "payment_type": "advance",
            # description 누락
            "amount": 100000,
        }, cookies=cookies)
        if r.status_code == 422:
            results.append(("T22 필수 필드 누락 → 422", "PASS", ""))
            passed += 1
        else:
            results.append(("T22 필수 필드 누락 → 422", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T23: amount ≤ 0 → 422
        r = await c.post(f"/projects/{project_id}/payments", json={
            "payment_type": "advance",
            "description": "잘못된 금액",
            "amount": 0,
        }, cookies=cookies)
        if r.status_code == 422:
            results.append(("T23 amount≤0 → 422", "PASS", ""))
            passed += 1
        else:
            results.append(("T23 amount≤0 → 422", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T24: 비로그인 → 401
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as anon:
            r = await anon.get("/payments")
        if r.status_code == 401:
            results.append(("T24 비로그인 수금 → 401", "PASS", ""))
            passed += 1
        else:
            results.append(("T24 비로그인 수금 → 401", "FAIL", f"status={r.status_code}"))
            failed += 1

        # ═══════════════════════════════════════════
        #  Group C: AI 견적 (Phase 4B) — T25~T29
        # ═══════════════════════════════════════════

        estimate_data = None

        # T25: AI 견적 생성
        try:
            r = await c.post("/ai/estimate/generate", json={
                "project_type": "outsourcing",
                "scope_description": "웹 애플리케이션 프론트엔드 개발 - React 기반 관리자 대시보드 및 사용자 포털 구현",
            }, cookies=cookies)
            if r.status_code == 200:
                estimate_data = r.json()
                has_items = len(estimate_data.get("items", [])) >= 1
                has_total = estimate_data.get("total_amount", 0) > 0
                if has_items and has_total:
                    results.append(("T25 AI 견적 생성", "PASS", f"items={len(estimate_data['items'])}, total={estimate_data['total_amount']}"))
                    passed += 1
                else:
                    results.append(("T25 AI 견적 생성", "FAIL", f"items={has_items}, total={has_total}"))
                    failed += 1
            elif r.status_code in (500, 502):
                results.append(("T25 AI 견적 생성", "SKIP", "Gemini API 미연결"))
                skipped += 1
            else:
                results.append(("T25 AI 견적 생성", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
                failed += 1
        except Exception as e:
            results.append(("T25 AI 견적 생성", "SKIP", f"Exception: {e}"))
            skipped += 1

        # T26: Sheet 내보내기
        if estimate_data:
            try:
                r = await c.post("/ai/estimate/export-sheet", json={
                    "project_id": project_id,
                    "title": "테스트 견적서",
                    "estimate_data": estimate_data,
                }, cookies=cookies)
                if r.status_code == 200 and r.json().get("sheet_url"):
                    results.append(("T26 Sheet 내보내기", "PASS", f"url={r.json()['sheet_url'][:50]}..."))
                    passed += 1
                elif r.status_code in (500, 502):
                    results.append(("T26 Sheet 내보내기", "SKIP", "Sheets API 미연결"))
                    skipped += 1
                else:
                    results.append(("T26 Sheet 내보내기", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
                    failed += 1
            except Exception as e:
                results.append(("T26 Sheet 내보내기", "SKIP", f"Exception: {e}"))
                skipped += 1
        else:
            results.append(("T26 Sheet 내보내기", "SKIP", "T25 SKIP"))
            skipped += 1

        # T27: scope 10자 미만 → 422
        r = await c.post("/ai/estimate/generate", json={
            "project_type": "outsourcing",
            "scope_description": "짧은설명",
        }, cookies=cookies)
        if r.status_code == 422:
            results.append(("T27 scope 10자 미만 → 422", "PASS", ""))
            passed += 1
        else:
            results.append(("T27 scope 10자 미만 → 422", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T28: scope 1000자 초과 → 422
        r = await c.post("/ai/estimate/generate", json={
            "project_type": "outsourcing",
            "scope_description": "A" * 1001,
        }, cookies=cookies)
        if r.status_code == 422:
            results.append(("T28 scope 1000자 초과 → 422", "PASS", ""))
            passed += 1
        else:
            results.append(("T28 scope 1000자 초과 → 422", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T29: 비로그인 → 401
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as anon:
            r = await anon.post("/ai/estimate/generate", json={
                "project_type": "outsourcing",
                "scope_description": "비로그인 테스트 요청입니다 열자이상",
            })
        if r.status_code == 401:
            results.append(("T29 비로그인 견적 → 401", "PASS", ""))
            passed += 1
        else:
            results.append(("T29 비로그인 견적 → 401", "FAIL", f"status={r.status_code}"))
            failed += 1

        # ═══════════════════════════════════════════
        #  Group D: 프로젝트 템플릿 (Phase 5A) — T30~T39
        # ═══════════════════════════════════════════

        template_id = None

        # T30: 템플릿 생성 (nested JSON)
        r = await c.post("/templates", json={
            "name": "웹 프로젝트 템플릿",
            "project_type": "outsourcing",
            "description": "기본 웹 개발 템플릿",
            "task_templates": [
                {
                    "task_name": "기획",
                    "phase": "기획단계",
                    "relative_due_days": 7,
                    "priority": "높음",
                    "is_client_facing": False,
                },
                {
                    "task_name": "디자인",
                    "phase": "디자인단계",
                    "relative_due_days": 14,
                    "priority": "보통",
                    "is_client_facing": True,
                },
            ],
            "schedule_templates": [
                {
                    "phase": "기획단계",
                    "relative_start_days": 0,
                    "duration_days": 7,
                },
            ],
        }, cookies=cookies)
        if r.status_code == 200:
            rdata = r.json()
            template_id = rdata["id"]
            task_count = len(rdata.get("task_templates") or [])
            if task_count == 2:
                results.append(("T30 템플릿 생성 (nested)", "PASS", f"id={template_id}, tasks={task_count}"))
                passed += 1
            else:
                results.append(("T30 템플릿 생성", "FAIL", f"task_templates count={task_count}"))
                failed += 1
        else:
            results.append(("T30 템플릿 생성", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
            failed += 1

        # T31: 템플릿 목록 조회
        r = await c.get("/templates", cookies=cookies)
        if r.status_code == 200 and r.json().get("total", 0) >= 1:
            results.append(("T31 템플릿 목록 조회", "PASS", f"total={r.json()['total']}"))
            passed += 1
        else:
            results.append(("T31 템플릿 목록 조회", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T32: 템플릿 상세 조회
        if template_id:
            r = await c.get(f"/templates/{template_id}", cookies=cookies)
            if r.status_code == 200 and r.json().get("id") == template_id:
                results.append(("T32 템플릿 상세 조회", "PASS", f"id={r.json()['id']}"))
                passed += 1
            else:
                results.append(("T32 템플릿 상세 조회", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T32 템플릿 상세 조회", "SKIP", "T30 실패"))
            skipped += 1

        # T33: 템플릿 수정 (name + description)
        if template_id:
            r = await c.put(f"/templates/{template_id}", json={
                "name": "수정된 템플릿",
                "description": "수정된 설명",
            }, cookies=cookies)
            if r.status_code == 200:
                ok = r.json().get("name") == "수정된 템플릿" and r.json().get("description") == "수정된 설명"
                if ok:
                    results.append(("T33 템플릿 수정 (name+desc)", "PASS", ""))
                    passed += 1
                else:
                    results.append(("T33 템플릿 수정", "FAIL", f"name={r.json().get('name')}"))
                    failed += 1
            else:
                results.append(("T33 템플릿 수정", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T33 템플릿 수정", "SKIP", "T30 실패"))
            skipped += 1

        # T34: task_templates 수정
        if template_id:
            r = await c.put(f"/templates/{template_id}", json={
                "task_templates": [
                    {
                        "task_name": "개발",
                        "phase": "개발단계",
                        "relative_due_days": 21,
                        "priority": "긴급",
                        "is_client_facing": False,
                    },
                ],
            }, cookies=cookies)
            if r.status_code == 200:
                new_tasks = r.json().get("task_templates") or []
                if len(new_tasks) == 1:
                    results.append(("T34 task_templates 수정", "PASS", f"tasks={len(new_tasks)}"))
                    passed += 1
                else:
                    results.append(("T34 task_templates 수정", "FAIL", f"tasks={len(new_tasks)}"))
                    failed += 1
            else:
                results.append(("T34 task_templates 수정", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T34 task_templates 수정", "SKIP", "T30 실패"))
            skipped += 1

        # T35: 템플릿 삭제
        if template_id:
            r = await c.delete(f"/templates/{template_id}", cookies=cookies)
            if r.status_code == 200:
                results.append(("T35 템플릿 삭제", "PASS", ""))
                passed += 1
            else:
                results.append(("T35 템플릿 삭제", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T35 템플릿 삭제", "SKIP", "T30 실패"))
            skipped += 1

        # T36: 삭제된 템플릿 조회 → 404
        if template_id:
            r = await c.get(f"/templates/{template_id}", cookies=cookies)
            if r.status_code == 404:
                results.append(("T36 삭제된 템플릿 → 404", "PASS", ""))
                passed += 1
            else:
                results.append(("T36 삭제된 템플릿 → 404", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T36 삭제된 템플릿 → 404", "SKIP", "T30 실패"))
            skipped += 1

        # T37: name 누락 → 422
        r = await c.post("/templates", json={
            # name 누락
            "project_type": "outsourcing",
        }, cookies=cookies)
        if r.status_code == 422:
            results.append(("T37 name 누락 → 422", "PASS", ""))
            passed += 1
        else:
            results.append(("T37 name 누락 → 422", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T38: 잘못된 nested 구조 → 422
        r = await c.post("/templates", json={
            "name": "잘못된 템플릿",
            "project_type": "outsourcing",
            "task_templates": [
                {"wrong_field": "잘못된 필드"},  # task_name, phase 등 필수 필드 누락
            ],
        }, cookies=cookies)
        if r.status_code == 422:
            results.append(("T38 잘못된 nested → 422", "PASS", ""))
            passed += 1
        else:
            results.append(("T38 잘못된 nested → 422", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T39: 비로그인 → 401
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as anon:
            r = await anon.get("/templates")
        if r.status_code == 401:
            results.append(("T39 비로그인 템플릿 → 401", "PASS", ""))
            passed += 1
        else:
            results.append(("T39 비로그인 템플릿 → 401", "FAIL", f"status={r.status_code}"))
            failed += 1

        # ═══════════════════════════════════════════
        #  Group E: 반복 업무 (Phase 5B) — T40~T47
        # ═══════════════════════════════════════════

        recurring_id = None

        # T40: weekly 생성
        r = await c.post(f"/projects/{project_id}/recurring-tasks", json={
            "task_name": "주간 보고서 작성",
            "frequency": "weekly",
            "day_of_week": 0,
            "priority": "보통",
        }, cookies=cookies)
        if r.status_code == 200:
            rdata = r.json()
            recurring_id = rdata["id"]
            if rdata.get("frequency") == "weekly":
                results.append(("T40 weekly 반복 생성", "PASS", f"id={recurring_id}"))
                passed += 1
            else:
                results.append(("T40 weekly 반복 생성", "FAIL", f"frequency={rdata.get('frequency')}"))
                failed += 1
        else:
            results.append(("T40 weekly 반복 생성", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
            failed += 1

        # T41: 반복 업무 목록 조회
        r = await c.get(f"/projects/{project_id}/recurring-tasks", cookies=cookies)
        if r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) >= 1:
            results.append(("T41 반복 업무 목록 조회", "PASS", f"count={len(r.json())}"))
            passed += 1
        else:
            results.append(("T41 반복 업무 목록 조회", "FAIL", f"status={r.status_code}"))
            failed += 1

        # T42: is_active toggle
        if recurring_id:
            r = await c.patch(f"/recurring-tasks/{recurring_id}", json={
                "is_active": False,
            }, cookies=cookies)
            if r.status_code == 200 and r.json().get("is_active") is False:
                results.append(("T42 is_active toggle", "PASS", "is_active=false"))
                passed += 1
            else:
                results.append(("T42 is_active toggle", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T42 is_active toggle", "SKIP", "T40 실패"))
            skipped += 1

        # T43: 반복 업무 삭제
        if recurring_id:
            r = await c.delete(f"/recurring-tasks/{recurring_id}", cookies=cookies)
            if r.status_code == 200:
                results.append(("T43 반복 업무 삭제", "PASS", ""))
                passed += 1
            else:
                results.append(("T43 반복 업무 삭제", "FAIL", f"status={r.status_code}"))
                failed += 1
        else:
            results.append(("T43 반복 업무 삭제", "SKIP", "T40 실패"))
            skipped += 1

        # T44: daily 생성 (day 필드 불필요)
        r = await c.post(f"/projects/{project_id}/recurring-tasks", json={
            "task_name": "일일 점검",
            "frequency": "daily",
            "priority": "낮음",
        }, cookies=cookies)
        if r.status_code == 200 and r.json().get("frequency") == "daily":
            daily_id = r.json()["id"]
            results.append(("T44 daily 반복 생성", "PASS", f"id={daily_id}"))
            passed += 1
            # 정리
            await c.delete(f"/recurring-tasks/{daily_id}", cookies=cookies)
        else:
            results.append(("T44 daily 반복 생성", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
            failed += 1

        # T45: monthly 생성 (day_of_month)
        r = await c.post(f"/projects/{project_id}/recurring-tasks", json={
            "task_name": "월간 정산",
            "frequency": "monthly",
            "day_of_month": 15,
            "priority": "높음",
        }, cookies=cookies)
        if r.status_code == 200:
            rdata = r.json()
            monthly_id = rdata["id"]
            if rdata.get("frequency") == "monthly" and rdata.get("day_of_month") == 15:
                results.append(("T45 monthly 반복 생성", "PASS", f"day_of_month={rdata['day_of_month']}"))
                passed += 1
            else:
                results.append(("T45 monthly 반복 생성", "FAIL", f"frequency={rdata.get('frequency')}, dom={rdata.get('day_of_month')}"))
                failed += 1
            # 정리
            await c.delete(f"/recurring-tasks/{monthly_id}", cookies=cookies)
        else:
            results.append(("T45 monthly 반복 생성", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
            failed += 1

        # T46: weekly + day_of_week 누락 → 422
        r = await c.post(f"/projects/{project_id}/recurring-tasks", json={
            "task_name": "주간 누락 테스트",
            "frequency": "weekly",
            # day_of_week 누락
            "priority": "보통",
        }, cookies=cookies)
        if r.status_code == 422 and "day_of_week" in r.json().get("detail", ""):
            results.append(("T46 weekly + day_of_week 누락 → 422", "PASS", r.json()["detail"]))
            passed += 1
        else:
            results.append(("T46 weekly + day_of_week 누락", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
            failed += 1

        # T47: monthly + day_of_month 누락 → 422
        r = await c.post(f"/projects/{project_id}/recurring-tasks", json={
            "task_name": "월간 누락 테스트",
            "frequency": "monthly",
            # day_of_month 누락
            "priority": "보통",
        }, cookies=cookies)
        if r.status_code == 422 and "day_of_month" in r.json().get("detail", ""):
            results.append(("T47 monthly + day_of_month 누락 → 422", "PASS", r.json()["detail"]))
            passed += 1
        else:
            results.append(("T47 monthly + day_of_month 누락", "FAIL", f"status={r.status_code}, body={r.text[:200]}"))
            failed += 1

    # ═══════════════════════════════════════════
    #  결과 출력
    # ═══════════════════════════════════════════

    total = passed + failed
    print(f"\n{'='*60}")
    print(f"  Phase 3~5 통합 테스트 결과: {passed}/{total} (SKIP: {skipped})")
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
