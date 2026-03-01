#!/usr/bin/env bash
# scripts/check-env.sh — Valida que las variables de entorno requeridas existan
# AI-35: Configurar gestión de secrets

set -e

ENV_FILE="$(dirname "$0")/../.env"

# Cargar .env si existe
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

REQUIRED_VARS=(
    DB_HOST
    DB_PORT
    DB_NAME
    DB_USER
    DB_PASSWORD
    REDIS_HOST
    REDIS_PORT
    LLM_API_KEY
)

MISSING=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING+=("$var")
    fi
done

if [ ${#MISSING[@]} -ne 0 ]; then
    echo "❌ Variables faltantes en .env:"
    printf '   - %s\n' "${MISSING[@]}"
    echo ""
    echo "  👉 Copia .env.example a .env y completa los valores reales."
    exit 1
fi

echo "✅ Todas las variables de entorno están configuradas."
