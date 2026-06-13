"""ai_usage + wa_conversations + wa_messages (feature 013)

Revision ID: 20260612180000
Revises: 20260408185900
Create Date: 2026-06-12 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260612180000"
down_revision: str | None = "20260408185900"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("session_id", sa.String(length=120), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])

    op.create_table(
        "wa_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("mode", sa.String(length=10), nullable=True),
        sa.Column("human_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_customer_msg_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone"),
    )
    op.create_index("ix_wa_conversations_phone", "wa_conversations", ["phone"])
    op.create_index(
        "ix_wa_conversations_last_activity_at", "wa_conversations", ["last_activity_at"]
    )

    op.create_table(
        "wa_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author", sa.String(length=10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["wa_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wa_messages_conversation_id", "wa_messages", ["conversation_id"])
    op.create_index("ix_wa_messages_created_at", "wa_messages", ["created_at"])


def downgrade() -> None:
    op.drop_table("wa_messages")
    op.drop_table("wa_conversations")
    op.drop_table("ai_usage")
