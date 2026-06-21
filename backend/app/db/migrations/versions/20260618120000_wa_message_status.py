"""wa_messages.wa_message_id + status (WhatsApp Fase 2 — delivery tracking)

Revision ID: 20260618120000
Revises: 20260613090000
Create Date: 2026-06-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260618120000"
down_revision: str | None = "20260613090000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("wa_messages", sa.Column("wa_message_id", sa.String(length=128), nullable=True))
    op.add_column("wa_messages", sa.Column("status", sa.String(length=10), nullable=True))
    op.create_index("ix_wa_messages_wa_message_id", "wa_messages", ["wa_message_id"])


def downgrade() -> None:
    op.drop_index("ix_wa_messages_wa_message_id", table_name="wa_messages")
    op.drop_column("wa_messages", "status")
    op.drop_column("wa_messages", "wa_message_id")
