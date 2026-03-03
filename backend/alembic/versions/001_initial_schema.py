"""Initial schema — all SkillNexus tables

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-03-03 06:42:00.000000

Schema Strategy:
- Adjacency List for RoadmapNode hierarchy (parent_id self-FK)
- Recursive CTEs used at query time to traverse the tree
- UUID primary keys throughout for distributed safety
- JSONB columns for flexible data (resources, extracted skills)
- Enum types for type-safe status fields
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Enum type definitions (reused in both op.create_table and standalone) ──────
# Using postgresql.ENUM with create_type=False everywhere inside op.create_table
# so SQLAlchemy never fires the auto-create event. We create them explicitly with
# checkfirst=True before the tables, making the migration fully idempotent.

_user_role = postgresql.ENUM(
    "learner", "admin", "manager", name="user_role", create_type=False
)
_point_event_type = postgresql.ENUM(
    "node_complete", "login", "streak_bonus", "quiz_pass", "resume_upload", "manual_award",
    name="point_event_type", create_type=False,
)
_node_status = postgresql.ENUM(
    "locked", "in_progress", "done", name="node_status", create_type=False
)
_assignment_status = postgresql.ENUM(
    "active", "completed", "archived", name="assignment_status", create_type=False
)
_chat_role = postgresql.ENUM(
    "user", "assistant", "system", name="chat_role", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Enum Types (idempotent — use checkfirst=True) ──────────────────────────
    postgresql.ENUM("learner", "admin", "manager", name="user_role").create(bind, checkfirst=True)
    postgresql.ENUM(
        "node_complete", "login", "streak_bonus", "quiz_pass", "resume_upload", "manual_award",
        name="point_event_type",
    ).create(bind, checkfirst=True)
    postgresql.ENUM("locked", "in_progress", "done", name="node_status").create(bind, checkfirst=True)
    postgresql.ENUM("active", "completed", "archived", name="assignment_status").create(bind, checkfirst=True)
    postgresql.ENUM("user", "assistant", "system", name="chat_role").create(bind, checkfirst=True)

    # ── Users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("role", _user_role, nullable=False, server_default="learner"),
        sa.Column("current_role_title", sa.String(150), nullable=True),
        sa.Column("xp_balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("streak_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_login_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── Refresh Tokens ─────────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)

    # ── Point Transactions ─────────────────────────────────────────────────────
    op.create_table(
        "point_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("event_type", _point_event_type, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reference_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_point_transactions_user_id", "point_transactions", ["user_id"])
    op.create_index("ix_point_transactions_user_created", "point_transactions", ["user_id", "created_at"])

    # ── Roadmaps ───────────────────────────────────────────────────────────────
    op.create_table(
        "roadmaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_roadmaps_title", "roadmaps", ["title"])

    # ── Roadmap Nodes (Adjacency List) ─────────────────────────────────────────
    op.create_table(
        "roadmap_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("roadmap_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("resources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("position_x", sa.Float(), nullable=False, server_default="0"),
        sa.Column("position_y", sa.Float(), nullable=False, server_default="0"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["roadmap_id"], ["roadmaps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["roadmap_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_roadmap_nodes_roadmap_id", "roadmap_nodes", ["roadmap_id"])
    op.create_index("ix_roadmap_nodes_parent_id", "roadmap_nodes", ["parent_id"])
    op.create_index("ix_roadmap_nodes_roadmap_parent", "roadmap_nodes", ["roadmap_id", "parent_id"])

    # ── User Roadmap Assignments ───────────────────────────────────────────────
    op.create_table(
        "user_roadmap_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("roadmap_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", _assignment_status, nullable=False, server_default="active"),
        sa.Column("completion_percentage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("strict_mode", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["roadmap_id"], ["roadmaps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "roadmap_id", name="uq_user_roadmap_assignment"),
    )
    op.create_index("ix_assignments_user", "user_roadmap_assignments", ["user_id"])
    op.create_index("ix_assignments_roadmap", "user_roadmap_assignments", ["roadmap_id"])

    # ── User Node Progress ─────────────────────────────────────────────────────
    op.create_table(
        "user_node_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("roadmap_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", _node_status, nullable=False, server_default="locked"),
        sa.Column("quiz_passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["roadmap_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["roadmap_id"], ["roadmaps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "node_id", name="uq_user_node_progress"),
    )
    op.create_index("ix_node_progress_user_roadmap", "user_node_progress", ["user_id", "roadmap_id"])

    # ── Chat Sessions ──────────────────────────────────────────────────────────
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("roadmap_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["roadmap_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["roadmap_id"], ["roadmaps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "node_id", name="uq_chat_session_user_node"),
    )
    op.create_index("ix_chat_sessions_user_node", "chat_sessions", ["user_id", "node_id"])

    # ── Chat Messages ──────────────────────────────────────────────────────────
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", _chat_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])

    # ── Resumes ────────────────────────────────────────────────────────────────
    op.create_table(
        "resumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("extracted_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("experience_years", sa.Float(), nullable=True),
        sa.Column("current_role_extracted", sa.String(150), nullable=True),
        sa.Column("suggested_roadmap_titles", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("processing_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resumes_user_id", "resumes", ["user_id"])

    # ── Auto-update triggers for updated_at ────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    for table in ["users", "roadmaps", "roadmap_nodes", "chat_sessions"]:
        op.execute(f"""
            CREATE TRIGGER update_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    # Drop triggers
    for table in ["users", "roadmaps", "roadmap_nodes", "chat_sessions"]:
        op.execute(f"DROP TRIGGER IF EXISTS update_{table}_updated_at ON {table};")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")

    # Drop tables (in reverse dependency order)
    op.drop_table("resumes")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("user_node_progress")
    op.drop_table("user_roadmap_assignments")
    op.drop_table("roadmap_nodes")
    op.drop_table("roadmaps")
    op.drop_table("point_transactions")
    op.drop_table("refresh_tokens")
    op.drop_table("users")

    # Drop enums
    bind = op.get_bind()
    for enum_name in ["user_role", "point_event_type", "node_status", "assignment_status", "chat_role"]:
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
