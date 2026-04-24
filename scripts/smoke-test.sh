#!/usr/bin/env bash
# =============================================================
# AI-Commerce Orchestrator — Smoke Test (AI-101)
# Verifica conectividad con DB, Redis y RabbitMQ desde el host.
# Uso: bash scripts/smoke-test.sh
# Retorna exit 0 si todo OK, exit 1 si algún servicio falla.
# =============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

# Cargar .env si existe
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-ai_commerce}"
RABBITMQ_MGMT_PORT="${RABBITMQ_MGMT_PORT:-15672}"
RABBITMQ_USER="${RABBITMQ_USER:-guest}"
RABBITMQ_PASS="${RABBITMQ_PASS:-guest}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"

PASS=0
FAIL=0

check() {
  local name="$1"
  local cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then
    echo "  ✅ $name"
    PASS=$((PASS + 1))
  else
    echo "  ❌ $name"
    FAIL=$((FAIL + 1))
  fi
}

echo ""
echo "=== Smoke Test — AI-Commerce Orchestrator ==="
echo ""

echo "▶ Base de datos (PostgreSQL)"
check "pg_isready en ${DB_HOST}:${DB_PORT}" \
  "pg_isready -h ${DB_HOST} -p ${DB_PORT} -U ${DB_USER} -d ${DB_NAME}"

check "Tablas base existen (products, orders, agent_events)" \
  "docker compose -f '${ROOT_DIR}/infra/docker-compose.yml' exec -T db psql -U ${DB_USER} -d ${DB_NAME} -tAc \"SELECT COUNT(*) FROM information_schema.tables WHERE table_name IN ('products','orders','agent_events') AND table_schema='public';\" | grep -q '^3\$'"

echo ""
echo "▶ Cache (Redis)"
check "Redis ping en container" \
  "docker compose -f '${ROOT_DIR}/infra/docker-compose.yml' exec -T redis redis-cli ping | grep -q PONG"

echo ""
echo "▶ Message Broker (RabbitMQ)"
check "Management API responde en puerto ${RABBITMQ_MGMT_PORT}" \
  "curl -sf -u ${RABBITMQ_USER}:${RABBITMQ_PASS} http://localhost:${RABBITMQ_MGMT_PORT}/api/healthchecks/node | grep -q '\"status\":\"ok\"'"

echo ""
echo "▶ Backend API"
check "GET /health → 200" \
  "curl -sf ${BACKEND_URL}/health | grep -q 'status'"

check "GET /metrics → Prometheus format" \
  "curl -sf ${BACKEND_URL}/metrics | grep -q 'http_requests_total'"

check "GET /products → 200" \
  "curl -sf '${BACKEND_URL}/products?per_page=1'"

echo ""
echo "================================================="
echo "  Resultados: ✅ $PASS pasaron | ❌ $FAIL fallaron"
echo "================================================="
echo ""

[ "$FAIL" -eq 0 ]
