"""자연어 명령 API — 6차 개발 Phase 4

POST /command/parse — 자연어 → 의도 파악 + 실행/확인 데이터 반환
"""
import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.endpoints.auth import require_current_user
from app.limiter import limiter
from app.services.command_service import parse_command, execute_command

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/command")


class CommandRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    context: dict | None = Field(None, description="현재 화면 맥락")


@router.post("/parse")
@limiter.limit("10/minute")
async def parse_natural_command(
    data: CommandRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """자연어 명령을 파싱하고 실행 또는 확인 데이터를 반환"""
    user = await require_current_user(request, db)

    # 1단계: 의도 파악
    command = await parse_command(data.message)
    if not command:
        return {
            "type": "text",
            "message": "명령을 이해하지 못했습니다. 다시 말씀해 주세요.",
        }

    # 2단계: 실행
    result = await execute_command(db, user, command, data.context)
    return result
