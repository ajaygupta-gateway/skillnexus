import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import BaseSchema, UUIDMixin


# ── Chat ───────────────────────────────────────────────────────────────────────
class ChatMessageRequest(BaseSchema):
    content: str = Field(min_length=1, max_length=4000)


class ChatMessageResponse(UUIDMixin, BaseSchema):
    session_id: uuid.UUID
    role: str  # user | assistant
    content: str
    created_at: datetime


class ChatSessionResponse(UUIDMixin, BaseSchema):
    user_id: uuid.UUID
    node_id: uuid.UUID
    roadmap_id: uuid.UUID
    node_title: str | None = None
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class ChatHistoryResponse(BaseSchema):
    session: ChatSessionResponse
    messages: list[ChatMessageResponse]


# ── Quiz ───────────────────────────────────────────────────────────────────────
class QuizOption(BaseSchema):
    key: str  # "A", "B", "C", "D"
    text: str


class QuizQuestion(BaseSchema):
    question_number: int
    question: str
    options: list[QuizOption]


class QuizResponse(BaseSchema):
    node_id: uuid.UUID
    node_title: str
    questions: list[QuizQuestion]
    total_questions: int = 3


class QuizAnswerSubmission(BaseSchema):
    answers: dict[str, str] = Field(
        description="Map of question_number (str) → selected option key (e.g. 'A')"
    )


class QuizResult(BaseSchema):
    score: int
    total: int
    passed: bool
    pass_threshold: int = 2
    node_id: uuid.UUID
    quiz_now_passed: bool  # True = first time passing
    can_mark_done: bool  # True if quiz_passed (for strict mode)
    feedback: str


# ── Resume ─────────────────────────────────────────────────────────────────────
class ResumeUploadResponse(UUIDMixin, BaseSchema):
    user_id: uuid.UUID
    original_filename: str
    processing_status: str
    extracted_skills: list[str] | None = None
    experience_years: float | None = None
    current_role_extracted: str | None = None
    suggested_roadmap_titles: list[str] | None = None
    processed_at: datetime | None = None
    created_at: datetime
