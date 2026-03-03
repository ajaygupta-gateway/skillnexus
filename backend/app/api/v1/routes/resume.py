"""Resume routes — PDF upload and AI skill extraction."""

from fastapi import APIRouter, File, UploadFile

from app.api.deps import CurrentUser, DB
from app.schemas.chat import ResumeUploadResponse
from app.services.resume_service import ResumeService

router = APIRouter(prefix="/resume", tags=["Resume"])


@router.post("/upload", response_model=ResumeUploadResponse, status_code=201)
async def upload_resume(
    current_user: CurrentUser,
    db: DB,
    file: UploadFile = File(...),
):
    """
    Upload a PDF resume. The system will:
    1. Extract text using pdfminer.six
    2. Use AI to extract skills, experience years, current role
    3. Suggest relevant learning roadmaps based on your profile
    4. Store results and return structured data

    Max file size: 10MB. Accepted format: PDF only.
    """
    file_bytes = await file.read()
    service = ResumeService(db)
    return await service.upload_and_process(
        user_id=current_user.id,
        filename=file.filename or "resume.pdf",
        content_type=file.content_type or "application/pdf",
        file_bytes=file_bytes,
    )


@router.get("/me", response_model=list[ResumeUploadResponse])
async def get_my_resumes(current_user: CurrentUser, db: DB):
    """Get the current user's resume upload history and extraction results."""
    service = ResumeService(db)
    return await service.get_user_resumes(current_user.id)
