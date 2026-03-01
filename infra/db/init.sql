-- =============================================================
-- AI-Commerce Orchestrator — Esquema base (AI-39)
-- Idempotente: usa IF NOT EXISTS en todos los objetos.
-- Se ejecuta automáticamente en el primer `docker compose up db`
-- (cuando el volumen de datos está vacío).
-- Para ejecutarlo manualmente:
--   docker compose -f infra/docker-compose.yml exec db \
--     psql -U postgres -d ai_commerce -f /docker-entrypoint-initdb.d/init.sql
-- =============================================================

BEGIN;

-- Tabla de productos sincronizados desde WooCommerce / fuentes externas
CREATE TABLE IF NOT EXISTS products (
    id          SERIAL PRIMARY KEY,
    external_id VARCHAR(255) NOT NULL,
    name        TEXT         NOT NULL,
    price       NUMERIC(12, 2) NOT NULL DEFAULT 0,
    stock       INTEGER        NOT NULL DEFAULT 0,
    source      VARCHAR(50)    NOT NULL DEFAULT 'woocommerce',
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_products_external_source UNIQUE (external_id, source)
);

-- Tabla de pedidos
CREATE TABLE IF NOT EXISTS orders (
    id          SERIAL PRIMARY KEY,
    external_id VARCHAR(255)   NOT NULL,
    status      VARCHAR(50)    NOT NULL DEFAULT 'pending',
    total       NUMERIC(12, 2) NOT NULL DEFAULT 0,
    source      VARCHAR(50)    NOT NULL DEFAULT 'woocommerce',
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_orders_external_source UNIQUE (external_id, source)
);

-- Tabla de eventos de agentes IA (auditoría / trazabilidad)
CREATE TABLE IF NOT EXISTS agent_events (
    id          BIGSERIAL   PRIMARY KEY,
    agent_name  VARCHAR(100) NOT NULL,
    event_type  VARCHAR(100) NOT NULL,
    payload     JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMIT;
