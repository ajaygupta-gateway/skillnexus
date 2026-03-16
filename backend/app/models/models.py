"""
SQLAlchemy ORM Models for SkillNexus.

Schema Strategy: Adjacency List for roadmap hierarchy.
Recursive CTEs are used at query time to traverse the tree.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────
class UserRole(str, enum.Enum):
    learner = "learner"
    admin = "admin"
    manager = "manager"


class PointEventType(str, enum.Enum):
    node_complete = "node_complete"
    login = "login"
    streak_bonus = "streak_bonus"
    quiz_pass = "quiz_pass"
    resume_upload = "resume_upload"
    manual_award = "manual_award"


class NodeStatus(str, enum.Enum):
    locked = "locked"
    in_progress = "in_progress"
    done = "done"


class AssignmentStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    archived = "archived"


class ChatRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


# ── User ──────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.learner, nullable=False
    )
    current_role_title: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # Gamification — cached balance for fast leaderboard queries
    xp_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Streak tracking
    streak_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_login_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    point_transactions: Mapped[list["PointTransaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    assignments: Mapped[list["UserRoadmapAssignment"]] = relationship(
        back_populates="user",
        foreign_keys="UserRoadmapAssignment.user_id",
        cascade="all, delete-orphan",
    )
    node_progress: Mapped[list["UserNodeProgress"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    created_roadmaps: Mapped[list["Roadmap"]] = relationship(
        back_populates="creator", foreign_keys="Roadmap.created_by"
    )
    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# ── RefreshToken ──────────────────────────────────────────────────────────────
class RefreshToken(Base):
    """Stateful refresh token store. Token is stored as SHA-256 hash."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


# ── PointTransaction ──────────────────────────────────────────────────────────
class PointTransaction(Base):
    """Event-based XP ledger. Append-only. Cached sum lives on User.xp_balance."""

    __tablename__ = "point_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # Can be negative
    event_type: Mapped[PointEventType] = mapped_column(
        Enum(PointEventType, name="point_event_type"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # e.g., node_id or roadmap_id
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="point_transactions")

    __table_args__ = (
        Index("ix_point_transactions_user_created", "user_id", "created_at"),
    )


# ── Roadmap ────────────────────────────────────────────────────────────────────
class Roadmap(Base):
    __tablename__ = "roadmaps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    creator: Mapped["User | None"] = relationship(
        back_populates="created_roadmaps", foreign_keys=[created_by]
    )
    nodes: Mapped[list["RoadmapNode"]] = relationship(
        back_populates="roadmap", cascade="all, delete-orphan"
    )
    assignments: Mapped[list["UserRoadmapAssignment"]] = relationship(
        back_populates="roadmap", cascade="all, delete-orphan"
    )


# ── RoadmapNode ────────────────────────────────────────────────────────────────
class RoadmapNode(Base):
    """
    Adjacency List tree structure.
    - parent_id = NULL means this is a root node.
    - Recursive CTEs traverse the tree at query time.
    - Supports 5-6+ levels deep efficiently.
    """

    __tablename__ = "roadmap_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    roadmap_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roadmaps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Self-referential FK for adjacency list
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # resources: list of {title, url, type} dicts
    resources: Mapped[list | None] = mapped_column(JSONB, default=list, nullable=True)
    # Visual positioning for frontend rendering
    position_x: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position_y: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    roadmap: Mapped["Roadmap"] = relationship(back_populates="nodes")

    # Self-referential relationships (Adjacency List)
    # children: all direct child nodes (cascade delete)
    children: Mapped[list["RoadmapNode"]] = relationship(
        "RoadmapNode",
        cascade="all, delete-orphan",
        foreign_keys="RoadmapNode.parent_id",
        back_populates="parent",
    )
    # parent: the single parent node (many-to-one side, remote_side required)
    parent: Mapped["RoadmapNode | None"] = relationship(
        "RoadmapNode",
        foreign_keys="RoadmapNode.parent_id",
        back_populates="children",
        remote_side="RoadmapNode.id",
    )

    progress_records: Mapped[list["UserNodeProgress"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_roadmap_nodes_roadmap_parent", "roadmap_id", "parent_id"),
    )


# ── UserRoadmapAssignment ──────────────────────────────────────────────────────
class UserRoadmapAssignment(Base):
    __tablename__ = "user_roadmap_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    roadmap_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roadmaps.id", ondelete="CASCADE"), nullable=False
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(AssignmentStatus, name="assignment_status"),
        default=AssignmentStatus.active,
        nullable=False,
    )
    completion_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    strict_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(
        back_populates="assignments", foreign_keys=[user_id]
    )
    roadmap: Mapped["Roadmap"] = relationship(back_populates="assignments")
    assigner: Mapped["User | None"] = relationship(foreign_keys=[assigned_by])

    __table_args__ = (
        UniqueConstraint("user_id", "roadmap_id", name="uq_user_roadmap_assignment"),
        Index("ix_assignments_user", "user_id"),
        Index("ix_assignments_roadmap", "roadmap_id"),
    )


# ── UserNodeProgress ───────────────────────────────────────────────────────────
class UserNodeProgress(Base):
    __tablename__ = "user_node_progress"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roadmap_nodes.id", ondelete="CASCADE"), nullable=False
    )
    roadmap_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roadmaps.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[NodeStatus] = mapped_column(
        Enum(NodeStatus, name="node_status"),
        default=NodeStatus.locked,
        nullable=False,
    )
    quiz_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="node_progress")
    node: Mapped["RoadmapNode"] = relationship(back_populates="progress_records")

    __table_args__ = (
        UniqueConstraint("user_id", "node_id", name="uq_user_node_progress"),
        Index("ix_node_progress_user_roadmap", "user_id", "roadmap_id"),
    )


# ── ChatSession ────────────────────────────────────────────────────────────────
class ChatSession(Base):
    """One chat session per (user, node) pair — persists full conversation history."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roadmap_nodes.id", ondelete="CASCADE"), nullable=False
    )
    roadmap_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roadmaps.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    node: Mapped["RoadmapNode"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "node_id", name="uq_chat_session_user_node"),
        Index("ix_chat_sessions_user_node", "user_id", "node_id"),
    )


# ── ChatMessage ────────────────────────────────────────────────────────────────
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[ChatRole] = mapped_column(
        Enum(ChatRole, name="chat_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


# ── Resume ─────────────────────────────────────────────────────────────────────
class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Structured extraction result from LLM
    extracted_skills: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_role_extracted: Mapped[str | None] = mapped_column(String(150), nullable=True)
    suggested_roadmap_titles: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending | done | failed
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="resumes")


# ── RoadmapRequest ─────────────────────────────────────────────────────────────
class RoadmapRequest(Base):
    """Tracks when a user requests a new roadmap based on resume suggestions."""

    __tablename__ = "roadmap_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending | fulfilled | rejected
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
