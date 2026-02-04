from fastapi import APIRouter, UploadFile, File, HTTPException

from app.services.file_service import FileService
from app.services.openai_service import OpenAIService
from app.schemas.schedule import ScheduleResponse

router = APIRouter()


@router.post("/upload-and-extract", response_model=ScheduleResponse)
async def upload_and_extract_schedule(
    file: UploadFile = File(..., description="계약서 파일 (PDF, DOCX, HWP)")
):
    """
    계약서 파일을 업로드하고 추진 일정을 추출합니다.

    - **file**: PDF, DOCX, HWP 형식의 계약서 파일

    Returns:
        - contract_schedule: 추출된 계약 일정 정보
        - task_list: 생성된 업무 목록
    """
    file_service = FileService()
    saved_path = None

    try:
        # 1. 파일 저장
        saved_path = await file_service.save_upload_file(file)

        # 2. 파일 파싱
        text_content = await file_service.parse_file(saved_path)

        if not text_content or not text_content.strip():
            raise HTTPException(
                status_code=400, detail="파일에서 텍스트를 추출할 수 없습니다."
            )

        # 3. OpenAI로 일정 추출
        openai_service = OpenAIService()
        contract_schedule, task_list = await openai_service.extract_schedule(text_content)

        return ScheduleResponse(
            success=True,
            message="일정 추출 완료",
            contract_schedule=contract_schedule,
            task_list=task_list,
            raw_text_preview=text_content[:500] if text_content else None,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"처리 중 오류가 발생했습니다: {str(e)}")
    finally:
        # 4. 임시 파일 정리
        if saved_path:
            await file_service.cleanup(saved_path)


@router.get("/health")
async def health_check():
    """서버 상태 확인"""
    return {"status": "ok", "message": "서버가 정상 작동 중입니다."}
