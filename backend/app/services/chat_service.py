"""
Chat Service — AI Tutor with persistent per-node chat history and quiz generation.

Prompt Strategy:
- System prompt contextualizes the AI as an expert corporate trainer
  anchored to the specific node being viewed.
- Chat history (last 5 messages) is loaded from DB and passed to LLM
  as LangChain message objects for full conversation continuity.
- Quiz generation uses structured output (Pydantic) to guarantee parseable JSON.
"""

import json
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, LLMException, NotFoundException
from app.models.models import ChatRole
from app.repositories.chat_repository import ChatRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.roadmap_repository import RoadmapRepository
from app.schemas.chat import (
    ChatHistoryResponse,
    ChatMessageResponse,
    ChatSessionResponse,
    QuizOption,
    QuizQuestion,
    QuizResponse,
    QuizResult,
)
from app.services.llm_factory import get_llm, get_structured_llm


# ── Pydantic schemas for structured LLM output ────────────────────────────────
class _QuizOptionSchema(BaseModel):
    key: str = Field(description="Option key: A, B, C, or D")
    text: str = Field(description="The option text")


class _QuizQuestionSchema(BaseModel):
    question_number: int
    question: str
    options: list[_QuizOptionSchema] = Field(min_length=4, max_length=4)
    correct_answer: str = Field(description="The correct option key: A, B, C, or D")


class _QuizSchema(BaseModel):
    questions: list[_QuizQuestionSchema] = Field(
        min_length=3, max_length=3, description="Exactly 3 questions"
    )


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.chat_repo = ChatRepository(db)
        self.roadmap_repo = RoadmapRepository(db)
        self.progress_repo = ProgressRepository(db)

    def _build_system_prompt(self, node_title: str, roadmap_title: str) -> str:
        return (
            f"You are an expert corporate trainer and mentor. "
            f"The user is CURRENTLY studying ONE specific topic: '{node_title}' "
            f"in the '{roadmap_title}' learning roadmap. "
            f"Your strict rules:\n"
            f"1. Explain concepts clearly and concisely regarding '{node_title}' only.\n"
            f"2. Use practical examples from real-world industry scenarios.\n"
            f"3. Break down complex topics into digestible chunks.\n"
            f"4. Encourage the learner and reinforce understanding.\n"
            f"5. IMPORTANT: Do NOT teach, explain, or answer questions about OTHER topics in the roadmap. "
            f"If the user asks about a different node (e.g. a future or past topic like 'Probability and Statistics' "
            f"when the current node is '{node_title}'), politely refuse, tell them to complete "
            f"the current topic first, and redirect them back to '{node_title}'.\n"
            f"6. When asked to quiz, generate exactly 3 multiple-choice questions."
        )

    async def get_or_create_session(
        self, user_id: uuid.UUID, node_id: uuid.UUID, roadmap_id: uuid.UUID
    ) -> ChatSessionResponse:
        node = await self.roadmap_repo.get_node_by_id(node_id)
        if not node:
            raise NotFoundException("Node")

        session, created = await self.chat_repo.get_or_create_session(
            user_id=user_id, node_id=node_id, roadmap_id=roadmap_id
        )
        count = await self.chat_repo.count_messages(session.id)

        return ChatSessionResponse(
            id=session.id,
            user_id=session.user_id,
            node_id=session.node_id,
            roadmap_id=session.roadmap_id,
            node_title=node.title,
            message_count=count,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    async def get_chat_history(
        self, user_id: uuid.UUID, node_id: uuid.UUID, roadmap_id: uuid.UUID
    ) -> ChatHistoryResponse:
        node = await self.roadmap_repo.get_node_by_id(node_id)
        if not node:
            raise NotFoundException("Node")

        session, _ = await self.chat_repo.get_or_create_session(
            user_id=user_id, node_id=node_id, roadmap_id=roadmap_id
        )

        messages = await self.chat_repo.get_messages(session.id)
        count = len(messages)

        session_response = ChatSessionResponse(
            id=session.id,
            user_id=session.user_id,
            node_id=session.node_id,
            roadmap_id=session.roadmap_id,
            node_title=node.title,
            message_count=count,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
        message_responses = [
            ChatMessageResponse(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ]
        return ChatHistoryResponse(session=session_response, messages=message_responses)

    async def send_message(
        self,
        user_id: uuid.UUID,
        node_id: uuid.UUID,
        roadmap_id: uuid.UUID,
        content: str,
    ) -> ChatMessageResponse:
        node = await self.roadmap_repo.get_node_by_id(node_id)
        if not node:
            raise NotFoundException("Node")
        roadmap = await self.roadmap_repo.get_by_id(roadmap_id)
        roadmap_title = roadmap.title if roadmap else "this roadmap"

        session, _ = await self.chat_repo.get_or_create_session(
            user_id=user_id, node_id=node_id, roadmap_id=roadmap_id
        )

        # Persist user message
        await self.chat_repo.add_message(
            session_id=session.id,
            role=ChatRole.user,
            content=content,
        )

        # Build LangChain message history
        system_prompt = self._build_system_prompt(node.title, roadmap_title)
        lc_messages = [SystemMessage(content=system_prompt)]

        # Load last 5 messages for context
        history = await self.chat_repo.get_recent_messages_for_context(
            session.id, limit=5
        )
        for msg in history:
            if msg.role == ChatRole.user:
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == ChatRole.assistant:
                lc_messages.append(AIMessage(content=msg.content))

        # Call LLM
        try:
            llm = get_llm()
            response = await llm.ainvoke(lc_messages)
            ai_content = response.content
        except Exception as e:
            raise LLMException(f"AI Tutor temporarily unavailable: {str(e)}")

        # Persist AI response
        ai_message = await self.chat_repo.add_message(
            session_id=session.id,
            role=ChatRole.assistant,
            content=ai_content,
        )

        return ChatMessageResponse(
            id=ai_message.id,
            session_id=ai_message.session_id,
            role=ai_message.role,
            content=ai_message.content,
            created_at=ai_message.created_at,
        )

    async def generate_quiz(
        self, user_id: uuid.UUID, node_id: uuid.UUID, roadmap_id: uuid.UUID
    ) -> QuizResponse:
        node = await self.roadmap_repo.get_node_by_id(node_id)
        if not node:
            raise NotFoundException("Node")

        prompt = (
            f"Generate exactly 3 multiple-choice quiz questions to test understanding of: "
            f"'{node.title}'.\n"
            f"Topic description: {node.description or 'General concepts related to ' + node.title}\n\n"
            f"Rules:\n"
            f"- Each question must have exactly 4 options (A, B, C, D)\n"
            f"- Questions should test practical understanding, not just memorization\n"
            f"- Vary difficulty: 1 easy, 1 medium, 1 hard\n"
            f"- Provide the correct_answer key for each question"
        )

        try:
            structured_llm = get_structured_llm(_QuizSchema)
            quiz_data: _QuizSchema = await structured_llm.ainvoke(prompt)
        except Exception as e:
            raise LLMException(f"Quiz generation failed: {str(e)}")

        # Store quiz answers in session for later validation
        # We store the correct answers in chat session as a system message
        session, _ = await self.chat_repo.get_or_create_session(
            user_id=user_id, node_id=node_id, roadmap_id=roadmap_id
        )
        answers_json = json.dumps(
            {str(q.question_number): q.correct_answer for q in quiz_data.questions}
        )
        # Store answers as a system message (hidden from user, used for validation)
        await self.chat_repo.add_message(
            session_id=session.id,
            role=ChatRole.system,
            content=f"__QUIZ_ANSWERS__:{answers_json}",
        )

        questions = [
            QuizQuestion(
                question_number=q.question_number,
                question=q.question,
                options=[QuizOption(key=o.key, text=o.text) for o in q.options],
            )
            for q in quiz_data.questions
        ]

        return QuizResponse(
            node_id=node_id,
            node_title=node.title,
            questions=questions,
            total_questions=3,
        )

    async def submit_quiz(
        self,
        user_id: uuid.UUID,
        node_id: uuid.UUID,
        roadmap_id: uuid.UUID,
        answers: dict[str, str],
    ) -> QuizResult:
        node = await self.roadmap_repo.get_node_by_id(node_id)
        if not node:
            raise NotFoundException("Node")

        session, _ = await self.chat_repo.get_or_create_session(
            user_id=user_id, node_id=node_id, roadmap_id=roadmap_id
        )

        # Find the latest stored quiz answers
        messages = await self.chat_repo.get_messages(session.id)
        correct_answers: dict[str, str] | None = None
        for msg in reversed(messages):
            if msg.role == ChatRole.system and msg.content.startswith("__QUIZ_ANSWERS__:"):
                answers_json = msg.content[len("__QUIZ_ANSWERS__:"):]
                correct_answers = json.loads(answers_json)
                break

        if not correct_answers:
            raise BadRequestException("No active quiz found. Please generate a quiz first.")

        # Grade answers
        score = 0
        for q_num, correct in correct_answers.items():
            submitted = answers.get(q_num, "").upper()
            if submitted == correct.upper():
                score += 1

        total = len(correct_answers)
        passed = score >= 2  # Pass threshold: 2 out of 3

        quiz_now_passed = False
        if passed:
            # Mark quiz as passed on node progress
            existing = await self.progress_repo.get_node_progress(user_id, node_id)
            quiz_now_passed = not existing or not existing.quiz_passed
            await self.progress_repo.mark_quiz_passed(user_id, node_id, roadmap_id)


        feedback = (
            f"🎉 Excellent! You scored {score}/{total}. You've demonstrated solid understanding of {node.title}!"
            if passed
            else f"You scored {score}/{total}. Review the material and try again — you need at least 2/3 to pass."
        )

        return QuizResult(
            score=score,
            total=total,
            passed=passed,
            pass_threshold=2,
            node_id=node_id,
            quiz_now_passed=quiz_now_passed,
            can_mark_done=passed,
            feedback=feedback,
        )