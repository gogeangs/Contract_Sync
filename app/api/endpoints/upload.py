from fastapi import APIRouter, UploadFile, File, HTTPException

from app.services.file_service import FileService
from app.services.gemini_service import GeminiService
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

        # 2. 파일 파싱 (텍스트 또는 이미지)
        parse_result = await file_service.parse_file(saved_path)

        if not parse_result.has_text and not parse_result.has_images:
            raise HTTPException(
                status_code=400, detail="파일에서 텍스트를 추출할 수 없습니다."
            )

        # 3. Gemini로 일정 추출
        gemini_service = GeminiService()
        contract_schedule, task_list, extracted_text = await gemini_service.extract_schedule(
            text=parse_result.text,
            images=parse_result.images if parse_result.has_images else None,
        )

        # 원문 텍스트: 파서 추출 텍스트 우선, 없으면 Gemini OCR 텍스트 사용
        raw_text = parse_result.text if parse_result.has_text else extracted_text

        return ScheduleResponse(
            success=True,
            message="일정 추출 완료",
            contract_schedule=contract_schedule,
            task_list=task_list,
            raw_text_preview=raw_text[:500] if raw_text else None,
            raw_text=raw_text,
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
