"""
Chat Repository — manages chat sessions and message history per node.
"""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import ChatMessage, ChatRole, ChatSession


class ChatRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_session(
        self,
        user_id: uuid.UUID,
        node_id: uuid.UUID,
        roadmap_id: uuid.UUID,
    ) -> tuple[ChatSession, bool]:
        """Get existing session or create a new one. Returns (session, created)."""
        result = await self.db.execute(
            select(ChatSession).where(
                ChatSession.user_id == user_id,
                ChatSession.node_id == node_id,
            )
        )
        session = result.scalar_one_or_none()
        if session:
            return session, False

        session = ChatSession(
            user_id=user_id,
            node_id=node_id,
            roadmap_id=roadmap_id,
        )
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session, True

    async def get_session_by_id(self, session_id: uuid.UUID) -> ChatSession | None:
        result = await self.db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_messages(
        self, session_id: uuid.UUID, limit: int = 50
    ) -> list[ChatMessage]:
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        return result.scalars().all()

    async def add_message(
        self,
        session_id: uuid.UUID,
        role: ChatRole,
        content: str,
    ) -> ChatMessage:
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
        )
        self.db.add(message)
        await self.db.flush()
        await self.db.refresh(message)
        return message

    async def count_messages(self, session_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.session_id == session_id
            )
        )
        return result.scalar_one()

    async def get_recent_messages_for_context(
        self, session_id: uuid.UUID, limit: int = 20
    ) -> list[ChatMessage]:
        """Get the most recent N messages for LLM context (to manage token limits)."""
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        messages = result.scalars().all()
        return list(reversed(messages))  # Chronological order for LLM

    async def delete_quiz_answer_messages(self, session_id: uuid.UUID) -> None:
        """
        Remove ALL previously stored __QUIZ_ANSWERS__ system messages for this session.
        Called before each new quiz generation so only one answer-key row ever exists,
        preventing duplicate rows caused by React StrictMode double-invoking effects.
        """
        await self.db.execute(
            delete(ChatMessage).where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == ChatRole.system,
                ChatMessage.content.like("__QUIZ_ANSWERS__%"),
            )
        )
        await self.db.flush()
