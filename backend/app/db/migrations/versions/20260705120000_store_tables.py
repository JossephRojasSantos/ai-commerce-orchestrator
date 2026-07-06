"""store_product / store_order — tienda headless Next.js (fase 2 migración WP)

Revision ID: 20260705120000
Revises: 20260618120000
Create Date: 2026-07-05 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260705120000"
down_revision: str | None = "20260618120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "store_product",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("anchor_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("short_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("dropi_product_id", sa.BigInteger(), nullable=True),
        sa.Column("dropi_supplier_id", sa.BigInteger(), nullable=True),
        sa.Column("supplier_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("images", sa.JSON(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("wc_product_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("wc_product_id"),
    )
    op.create_index("ix_store_product_slug", "store_product", ["slug"])
    op.create_index("ix_store_product_dropi_product_id", "store_product", ["dropi_product_id"])
    op.create_index("ix_store_product_active", "store_product", ["active"])

    op.create_table(
        "store_order",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shop_order_id", sa.Text(), nullable=False),
        sa.Column("dropi_order_id", sa.BigInteger(), nullable=True),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="PENDIENTE CONFIRMACION"),
        sa.Column("customer", sa.JSON(), nullable=False),
        sa.Column("products", sa.JSON(), nullable=False),
        sa.Column("dropi_payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_order_id"),
    )
    op.create_index("ix_store_order_dropi_order_id", "store_order", ["dropi_order_id"])
    op.create_index("ix_store_order_created_at", "store_order", ["created_at"])


def downgrade() -> None:
    op.drop_table("store_order")
    op.drop_table("store_product")
