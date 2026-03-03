"""Chat routes — AI Tutor, quiz generation, and quiz submission."""

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DB
from app.schemas.chat import (
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionResponse,
    QuizAnswerSubmission,
    QuizResponse,
    QuizResult,
)
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["AI Tutor"])


@router.get("/sessions/{node_id}", response_model=ChatSessionResponse)
async def get_or_create_session(
    node_id: uuid.UUID,
    roadmap_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    """
    Get existing chat session for the current user + node, or create one.
    The frontend should call this when a user opens a node to initialize context.
    """
    service = ChatService(db)
    return await service.get_or_create_session(
        user_id=current_user.id,
        node_id=node_id,
        roadmap_id=roadmap_id,
    )


@router.get("/sessions/{node_id}/messages", response_model=ChatHistoryResponse)
async def get_chat_history(
    node_id: uuid.UUID,
    roadmap_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    """Get full chat conversation history for this user + node."""
    service = ChatService(db)
    return await service.get_chat_history(
        user_id=current_user.id,
        node_id=node_id,
        roadmap_id=roadmap_id,
    )


@router.post("/sessions/{node_id}/messages", response_model=ChatMessageResponse)
async def send_message(
    node_id: uuid.UUID,
    roadmap_id: uuid.UUID,
    data: ChatMessageRequest,
    current_user: CurrentUser,
    db: DB,
):
    """
    Send a message to the AI Tutor for this node's context.

    The AI is automatically prompted with:
    'You are an expert corporate trainer. The user is currently studying [Node Topic].'

    Chat history from previous messages is included in the context.
    """
    service = ChatService(db)
    return await service.send_message(
        user_id=current_user.id,
        node_id=node_id,
        roadmap_id=roadmap_id,
        content=data.content,
    )


@router.post("/sessions/{node_id}/quiz", response_model=QuizResponse)
async def generate_quiz(
    node_id: uuid.UUID,
    roadmap_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    """
    Generate a 3-question multiple-choice quiz for the current node.

    The AI creates questions based on the node's title and description.
    Answers are securely stored server-side for validation.
    """
    service = ChatService(db)
    return await service.generate_quiz(
        user_id=current_user.id,
        node_id=node_id,
        roadmap_id=roadmap_id,
    )


@router.post("/sessions/{node_id}/quiz/submit", response_model=QuizResult)
async def submit_quiz(
    node_id: uuid.UUID,
    roadmap_id: uuid.UUID,
    data: QuizAnswerSubmission,
    current_user: CurrentUser,
    db: DB,
):
    """
    Submit quiz answers for validation.

    Pass threshold: 2/3 questions correct.
    On passing:
    - Node marked as quiz_passed (required for Strict Mode)
    - 25 XP awarded
    - Response indicates canMarkDone = True
    """
    service = ChatService(db)
    return await service.submit_quiz(
        user_id=current_user.id,
        node_id=node_id,
        roadmap_id=roadmap_id,
        answers=data.answers,
    )
