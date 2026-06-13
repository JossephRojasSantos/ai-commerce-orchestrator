"""scout_* — snapshots Dropi, señales, scores IA, demanda, runs (feature 014)

Revision ID: 20260613090000
Revises: 20260612180000
Create Date: 2026-06-13 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260613090000"
down_revision: str | None = "20260612180000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scout_product_snapshot",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dropi_product_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("supplier_name", sa.Text(), nullable=True),
        sa.Column("supplier_plan", sa.Text(), nullable=True),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("suggested_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("stock_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description_excerpt", sa.Text(), nullable=True),
        sa.Column("dropi_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dropi_product_id", "snapshot_date"),
    )
    op.create_index(
        "ix_scout_product_snapshot_dropi_product_id", "scout_product_snapshot", ["dropi_product_id"]
    )
    op.create_index(
        "ix_scout_product_snapshot_snapshot_date", "scout_product_snapshot", ["snapshot_date"]
    )

    op.create_table(
        "scout_signal",
        sa.Column("dropi_product_id", sa.BigInteger(), nullable=False),
        sa.Column("margin_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("velocity_7d", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_novelty", sa.Boolean(), nullable=True),
        sa.Column("is_viable", sa.Boolean(), nullable=True),
        sa.Column("rank_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("last_seen_date", sa.Date(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("dropi_product_id"),
    )
    op.create_index("ix_scout_signal_last_seen_date", "scout_signal", ["last_seen_date"])

    op.create_table(
        "scout_ai_score",
        sa.Column("dropi_product_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("dropi_product_id"),
    )

    op.create_table(
        "scout_demand_term",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("mention_count", sa.Integer(), nullable=True),
        sa.Column("sample_channels", sa.JSON(), nullable=True),
        sa.Column("matched_own_catalog", sa.Boolean(), nullable=True),
        sa.Column("dropi_candidates", sa.JSON(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term"),
    )

    op.create_table(
        "scout_ingest_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=True),
        sa.Column("processed", sa.Integer(), nullable=True),
        sa.Column("failed", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("scout_ingest_run")
    op.drop_table("scout_demand_term")
    op.drop_table("scout_ai_score")
    op.drop_table("scout_signal")
    op.drop_index(
        "ix_scout_product_snapshot_snapshot_date", table_name="scout_product_snapshot"
    )
    op.drop_index(
        "ix_scout_product_snapshot_dropi_product_id", table_name="scout_product_snapshot"
    )
    op.drop_table("scout_product_snapshot")
