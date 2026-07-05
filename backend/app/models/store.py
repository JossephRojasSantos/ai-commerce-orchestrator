"""Store headless — productos y copia de órdenes para la tienda Next.js (fase 2 migración).

`store_product` es la fuente de verdad del contenido de la tienda una vez muera
WordPress: precios de venta, galería, reseñas (feature 019), FAQ, comparativa,
escasez y demás secciones editables viven aquí. El script
`scripts/migrate_wc_products.py` puebla estas filas desde WooCommerce.

`store_order` es la copia local de cada orden creada en Dropi por el checkout
Next.js — Dropi sigue siendo la fuente operativa (guías, tracking).
"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StoreProduct(Base):
    """Producto publicable en la tienda headless."""

    __tablename__ = "store_product"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    anchor_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    short_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Integración Dropi — necesarios para crear la orden (products[].id / supplier_id)
    dropi_product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    dropi_supplier_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    supplier_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Galería: lista de URLs
    images: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Secciones editables (feature 019): reviews, faq, comparativa, escasez,
    # benefits, includes, warranty, use_case, size, badge, rating, landing…
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    # id del post WordPress de origen (trazabilidad de la migración)
    wc_product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StoreOrder(Base):
    """Copia local de una orden creada en Dropi por el checkout Next.js."""

    __tablename__ = "store_order"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shop_order_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    dropi_order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDIENTE CONFIRMACION")
    customer: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    products: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Respuesta cruda de Dropi al crear la orden (auditoría)
    dropi_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
