"""wa_messages: columnas de adjunto (imagen/documento) para el inbox admin

Revision ID: 20260821230000
Revises: 20260705120000
Create Date: 2026-08-21 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260821230000"
down_revision: str | None = "20260705120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("wa_messages", sa.Column("media_id", sa.String(length=256), nullable=True))
    op.add_column("wa_messages", sa.Column("media_type", sa.String(length=16), nullable=True))
    op.add_column("wa_messages", sa.Column("media_mime", sa.String(length=128), nullable=True))
    op.add_column("wa_messages", sa.Column("media_filename", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("wa_messages", "media_filename")
    op.drop_column("wa_messages", "media_mime")
    op.drop_column("wa_messages", "media_type")
    op.drop_column("wa_messages", "media_id")
