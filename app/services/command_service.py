"""자연어 명령 실행 서비스 — 6차 개발 Phase 4

Gemini로 사용자 의도를 파악하고 기존 API를 호출하여 업무 처리.
읽기 작업은 즉시 실행, 쓰기 작업은 확인 데이터를 반환.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import (
    User, Task, Project, Client, TeamMember,
)

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# ── Function 정의 (Gemini에 전달) ──

FUNCTION_DECLARATIONS = [
    {
        "name": "create_task",
        "description": "새 업무를 생성합니다",
        "parameters": {
            "type": "object",
            "properties": {
                "task_name": {"type": "string", "description": "업무 이름"},
                "project_name": {"type": "string", "description": "프로젝트 이름 (검색용)"},
                "due_date": {"type": "string", "description": "마감일 (YYYY-MM-DD)"},
                "priority": {"type": "string", "enum": ["높음", "보통", "낮음"], "description": "우선순위"},
                "assignee_name": {"type": "string", "description": "담당자 이름"},
            },
            "required": ["task_name"],
        },
    },
    {
        "name": "update_task",
        "description": "기존 업무를 수정합니다",
        "parameters": {
            "type": "object",
            "properties": {
                "task_name": {"type": "string", "description": "업무 이름 (검색용)"},
                "status": {"type": "string", "description": "변경할 상태"},
                "due_date": {"type": "string", "description": "변경할 마감일 (YYYY-MM-DD)"},
                "priority": {"type": "string", "description": "변경할 우선순위"},
                "assignee_name": {"type": "string", "description": "변경할 담당자 이름"},
            },
            "required": ["task_name"],
        },
    },
    {
        "name": "query_data",
        "description": "데이터를 조회합니다 (업무, 프로젝트, 발주처, 출퇴근 등)",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "enum": ["tasks", "projects", "clients", "attendance"]},
                "filter_text": {"type": "string", "description": "검색 조건 텍스트"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "navigate",
        "description": "특정 페이지로 이동합니다",
        "parameters": {
            "type": "object",
            "properties": {
                "page": {"type": "string", "description": "이동할 페이지 hash (예: #/my-tasks, #/payments)"},
            },
            "required": ["page"],
        },
    },
    {
        "name": "check_in_out",
        "description": "출퇴근을 기록합니다",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["check_in", "check_out"]},
            },
            "required": ["action"],
        },
    },
]


async def parse_command(message: str) -> dict | None:
    """Gemini로 사용자 의도 파악 → function call 결과 반환"""
    if not settings.gemini_api_key:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)

        # Gemini에 function declaration 전달
        tools = [types.Tool(function_declarations=[
            types.FunctionDeclaration(**fd) for fd in FUNCTION_DECLARATIONS
        ])]

        now_kst = datetime.now(KST)
        system_instruction = (
            f"오늘 날짜: {now_kst.strftime('%Y-%m-%d')} ({['월','화','수','목','금','토','일'][now_kst.weekday()]}요일). "
            "사용자의 자연어 명령을 분석하여 적절한 함수를 호출하세요. "
            "'내일'은 +1일, '금요일'은 다음 금요일, '3일 후'는 +3일로 계산하세요. "
            "미지정 시 priority는 '보통'을 기본값으로 사용하세요."
        )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            temperature=0.1,
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Content(role="user", parts=[types.Part(text=message)])],
            config=config,
        )

        # function call 추출
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    fc = part.function_call
                    return {
                        "action": fc.name,
                        "params": dict(fc.args) if fc.args else {},
                    }

        return None

    except Exception as e:
        logger.error(f"자연어 명령 파싱 실패: {e}")
        return None


async def execute_command(
    db: AsyncSession, user: User, command: dict,
    page_context: dict | None = None,
) -> dict:
    """파싱된 명령을 실행하고 결과를 반환"""
    action = command["action"]
    params = command["params"]

    if action == "navigate":
        return {
            "type": "navigate",
            "page": params.get("page", "#/dashboard"),
            "message": f'{params.get("page", "대시보드")} 페이지로 이동합니다',
        }

    if action == "check_in_out":
        is_check_in = params.get("action") == "check_in"
        return {
            "type": "action",
            "action": params.get("action", "check_in"),
            "message": f"{'출근' if is_check_in else '퇴근'} 처리를 요청합니다",
            "api": f"/api/v1/attendance/{'check-in' if is_check_in else 'check-out'}",
            "method": "POST",
        }

    if action == "query_data":
        return await _execute_query(db, user, params)

    if action == "create_task":
        return await _prepare_create_task(db, user, params, page_context)

    if action == "update_task":
        return await _prepare_update_task(db, user, params)

    return {"type": "error", "message": "인식할 수 없는 명령입니다"}


async def _execute_query(db: AsyncSession, user: User, params: dict) -> dict:
    """읽기 작업 즉시 실행"""
    target = params.get("target", "tasks")

    if target == "tasks":
        tasks = await db.execute(
            select(Task).where(
                Task.assignee_id == user.id,
                Task.status.notin_(["completed", "confirmed"]),
            ).order_by(Task.due_date.asc()).limit(10)
        )
        items = [{"id": t.id, "name": t.task_name, "due_date": t.due_date,
                  "status": t.status, "priority": t.priority}
                 for t in tasks.scalars().all()]
        return {"type": "data", "target": target, "items": items,
                "message": f"미완료 업무 {len(items)}건입니다"}

    elif target == "projects":
        team_ids_result = await db.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == user.id)
        )
        team_ids = [r[0] for r in team_ids_result.all()]
        from app.services.common import access_filter
        projects = await db.execute(
            select(Project).where(
                access_filter(Project, user.id, team_ids),
                Project.status.in_(["active", "planning"]),
            ).limit(10)
        )
        items = [{"id": p.id, "name": p.project_name, "status": p.status}
                 for p in projects.scalars().all()]
        return {"type": "data", "target": target, "items": items,
                "message": f"진행 중 프로젝트 {len(items)}건입니다"}

    elif target == "clients":
        clients = await db.execute(
            select(Client).limit(10)
        )
        items = [{"id": c.id, "name": c.name, "email": c.contact_email,
                  "phone": c.contact_phone}
                 for c in clients.scalars().all()]
        return {"type": "data", "target": target, "items": items,
                "message": f"발주처 {len(items)}건입니다"}

    return {"type": "data", "target": target, "items": [], "message": "데이터가 없습니다"}


async def _prepare_create_task(
    db: AsyncSession, user: User, params: dict,
    page_context: dict | None = None,
) -> dict:
    """업무 생성 — 확인 데이터 반환 (실제 생성은 프론트에서 API 호출)"""
    task_name = params.get("task_name", "")
    due_date = params.get("due_date")
    priority = params.get("priority", "보통")
    project_name = params.get("project_name")
    assignee_name = params.get("assignee_name")

    # 프로젝트 자동 추론
    project_id = None
    resolved_project = None
    if project_name:
        proj_result = await db.execute(
            select(Project).where(Project.project_name.contains(project_name)).limit(1)
        )
        proj = proj_result.scalar_one_or_none()
        if proj:
            project_id = proj.id
            resolved_project = proj.project_name
    elif page_context and page_context.get("page") == "projectDetail":
        pid = page_context.get("params", {}).get("id")
        if pid:
            proj = await db.get(Project, int(pid))
            if proj:
                project_id = proj.id
                resolved_project = proj.project_name

    # 담당자 추론
    assignee_id = None
    resolved_assignee = None
    if assignee_name:
        user_result = await db.execute(
            select(User).where(User.name.contains(assignee_name)).limit(1)
        )
        found_user = user_result.scalar_one_or_none()
        if found_user:
            assignee_id = found_user.id
            resolved_assignee = found_user.name

    return {
        "type": "confirm",
        "action": "create_task",
        "message": "다음 업무를 생성할까요?",
        "data": {
            "task_name": task_name,
            "project_id": project_id,
            "project_name": resolved_project,
            "due_date": due_date,
            "priority": priority,
            "assignee_id": assignee_id,
            "assignee_name": resolved_assignee,
        },
        "api": "/api/v1/tasks",
        "method": "POST",
    }


async def _prepare_update_task(db: AsyncSession, user: User, params: dict) -> dict:
    """업무 수정 — 확인 데이터 반환"""
    task_name = params.get("task_name", "")

    # 업무 검색
    task_result = await db.execute(
        select(Task).where(
            Task.assignee_id == user.id,
            Task.task_name.contains(task_name),
        ).limit(1)
    )
    task = task_result.scalar_one_or_none()

    if not task:
        # 유사 검색
        all_tasks = await db.execute(
            select(Task).where(Task.assignee_id == user.id).limit(20)
        )
        suggestions = [t.task_name for t in all_tasks.scalars().all()
                       if task_name.lower() in t.task_name.lower()]
        if suggestions:
            return {
                "type": "error",
                "message": f"'{task_name}'을 찾을 수 없어요. 혹시 다음 중 하나를 말씀하시나요?",
                "suggestions": suggestions[:5],
            }
        return {"type": "error", "message": f"'{task_name}' 업무를 찾을 수 없습니다"}

    changes = {}
    if params.get("status"):
        changes["status"] = params["status"]
    if params.get("due_date"):
        changes["due_date"] = params["due_date"]
    if params.get("priority"):
        changes["priority"] = params["priority"]

    # 담당자 변경
    if params.get("assignee_name"):
        user_result = await db.execute(
            select(User).where(User.name.contains(params["assignee_name"])).limit(1)
        )
        found = user_result.scalar_one_or_none()
        if found:
            changes["assignee_id"] = found.id
            changes["assignee_name"] = found.name

    return {
        "type": "confirm",
        "action": "update_task",
        "message": f"'{task.task_name}' 업무를 수정할까요?",
        "data": {
            "task_id": task.id,
            "task_name": task.task_name,
            "changes": changes,
        },
        "api": f"/api/v1/tasks/{task.id}",
        "method": "PATCH",
    }
