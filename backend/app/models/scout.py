"""Product Scout — snapshots Dropi, señales, scores IA y demanda (feature 014)."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScoutSnapshot(Base):
    """Estado diario de un producto Dropi; inmutable entre días (FR-002)."""

    __tablename__ = "scout_product_snapshot"
    __table_args__ = (UniqueConstraint("dropi_product_id", "snapshot_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dropi_product_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    suggested_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    stock_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    dropi_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ScoutSignal(Base):
    """Señales derivadas, 1 fila por producto, recalculadas tras cada ingesta."""

    __tablename__ = "scout_signal"

    dropi_product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    margin_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    velocity_7d: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_novelty: Mapped[bool] = mapped_column(Boolean, default=False)
    is_viable: Mapped[bool] = mapped_column(Boolean, default=True)
    rank_score: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    last_seen_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScoutAiScore(Base):
    """Evaluación LLM de aptitud COD; reusada mientras el contenido no cambie (FR-009)."""

    __tablename__ = "scout_ai_score"

    dropi_product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ScoutDemandTerm(Base):
    """Término de producto pedido en conversaciones, con match contra catálogos."""

    __tablename__ = "scout_demand_term"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, default=1)
    sample_channels: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    matched_own_catalog: Mapped[bool] = mapped_column(Boolean, default=False)
    dropi_candidates: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ScoutIngestRun(Base):
    """Registro operativo de ejecuciones (ingest | score | demand) — FR-015."""

    __tablename__ = "scout_ingest_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # ingest | score | demand
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="running")  # running | ok | error
    processed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
