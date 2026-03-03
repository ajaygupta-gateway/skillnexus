"""
Resume Service — PDF upload, text extraction, and AI-powered skill extraction.

Pipeline:
1. Validate file (PDF only, size limit)
2. Save to disk
3. Extract text with pdfminer.six
4. Call LLM with structured output → ExtractedResumeSchema
5. Persist results to Resume table
6. Return extracted data + roadmap suggestions
"""

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    FileTooLargeException,
    InvalidFileTypeException,
    LLMException,
    NotFoundException,
)
from app.models.models import Resume
from app.repositories.roadmap_repository import RoadmapRepository
from app.schemas.chat import ResumeUploadResponse
from app.services.llm_factory import get_structured_llm


# ── Structured output schema for LLM extraction ───────────────────────────────
class _ExtractedResumeSchema(BaseModel):
    skills: list[str] = Field(
        description="List of technical and professional skills found in the resume",
        default_factory=list,
    )
    experience_years: float = Field(
        description="Total years of professional experience (estimate)", default=0.0
    )
    current_role: str = Field(
        description="Current or most recent job title", default=""
    )
    suggested_roadmap_titles: list[str] = Field(
        description=(
            "3-5 learning roadmap titles best suited for this candidate based on their skills. "
            "Examples: 'React Developer', 'Backend Python Engineer', 'DevOps Engineer', "
            "'Data Science Fundamentals', 'Cloud Architecture'"
        ),
        default_factory=list,
    )
    summary: str = Field(
        description="Brief 2-3 sentence professional summary of the candidate",
        default="",
    )


def _extract_text_from_pdf(file_path: str) -> str:
    """Extract raw text from a PDF file using pdfminer.six."""
    from pdfminer.high_level import extract_text as pdfminer_extract

    try:
        text = pdfminer_extract(file_path)
        return text.strip()
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {str(e)}")


class ResumeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.roadmap_repo = RoadmapRepository(db)

    async def upload_and_process(
        self,
        user_id: uuid.UUID,
        filename: str,
        content_type: str,
        file_bytes: bytes,
    ) -> ResumeUploadResponse:
        # ── Validate ───────────────────────────────────────────────────────────
        if content_type not in ("application/pdf", "application/octet-stream"):
            if not filename.lower().endswith(".pdf"):
                raise InvalidFileTypeException("PDF")

        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if len(file_bytes) > max_bytes:
            raise FileTooLargeException(settings.MAX_FILE_SIZE_MB)

        # ── Save file ──────────────────────────────────────────────────────────
        upload_dir = Path(settings.UPLOAD_DIR) / "resumes" / str(user_id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        safe_name = f"{uuid.uuid4().hex}_{filename.replace(' ', '_')}"
        file_path = upload_dir / safe_name
        file_path.write_bytes(file_bytes)

        # ── Create pending DB record ───────────────────────────────────────────
        resume = Resume(
            user_id=user_id,
            file_path=str(file_path),
            original_filename=filename,
            processing_status="processing",
        )
        self.db.add(resume)
        await self.db.flush()
        await self.db.refresh(resume)

        # ── Extract text ───────────────────────────────────────────────────────
        try:
            raw_text = _extract_text_from_pdf(str(file_path))
            resume.raw_text = raw_text
        except Exception as e:
            resume.processing_status = "failed"
            self.db.add(resume)
            await self.db.flush()
            raise LLMException(f"PDF text extraction failed: {str(e)}")

        # ── LLM extraction ─────────────────────────────────────────────────────
        try:
            extraction_prompt = (
                f"Analyze the following resume text and extract structured information.\n\n"
                f"RESUME TEXT:\n{raw_text[:8000]}\n\n"  # Cap at 8K chars to stay within context
                f"Extract: skills list, years of experience, current role, "
                f"and suggest 3-5 relevant learning roadmaps for this candidate."
            )

            structured_llm = get_structured_llm(_ExtractedResumeSchema)
            extracted: _ExtractedResumeSchema = await structured_llm.ainvoke(
                extraction_prompt
            )

            resume.extracted_skills = extracted.skills
            resume.experience_years = extracted.experience_years
            resume.current_role_extracted = extracted.current_role
            resume.suggested_roadmap_titles = extracted.suggested_roadmap_titles
            resume.processing_status = "done"
            resume.processed_at = datetime.now(UTC)

        except Exception as e:
            resume.processing_status = "failed"
            self.db.add(resume)
            await self.db.flush()
            raise LLMException(f"AI skill extraction failed: {str(e)}")

        self.db.add(resume)
        await self.db.flush()
        await self.db.refresh(resume)

        return ResumeUploadResponse(
            id=resume.id,
            user_id=resume.user_id,
            original_filename=resume.original_filename,
            processing_status=resume.processing_status,
            extracted_skills=resume.extracted_skills,
            experience_years=resume.experience_years,
            current_role_extracted=resume.current_role_extracted,
            suggested_roadmap_titles=resume.suggested_roadmap_titles,
            processed_at=resume.processed_at,
            created_at=resume.created_at,
        )

    async def get_user_resumes(self, user_id: uuid.UUID) -> list[ResumeUploadResponse]:
        from sqlalchemy import select

        result = await self.db.execute(
            select(Resume)
            .where(Resume.user_id == user_id)
            .order_by(Resume.created_at.desc())
        )
        resumes = result.scalars().all()
        return [
            ResumeUploadResponse(
                id=r.id,
                user_id=r.user_id,
                original_filename=r.original_filename,
                processing_status=r.processing_status,
                extracted_skills=r.extracted_skills,
                experience_years=r.experience_years,
                current_role_extracted=r.current_role_extracted,
                suggested_roadmap_titles=r.suggested_roadmap_titles,
                processed_at=r.processed_at,
                created_at=r.created_at,
            )
            for r in resumes
        ]
