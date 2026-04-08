#!/usr/bin/env bash
# scripts/sync-env.sh — Sincroniza .env con claves faltantes desde .env.example

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
ENV_EXAMPLE="${ROOT_DIR}/.env.example"

if [ ! -f "$ENV_EXAMPLE" ]; then
    echo "❌ No se encontró ${ENV_EXAMPLE}."
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "  ✅ .env creado desde .env.example."
    exit 0
fi

TMP_KEYS="$(mktemp)"
trap 'rm -f "$TMP_KEYS"' EXIT

awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/{print $1}' "$ENV_FILE" | sort -u > "$TMP_KEYS"

ADDED=0
while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
        ""|\#*)
            continue
            ;;
    esac

    key="${line%%=*}"
    if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        continue
    fi

    if ! grep -qx "$key" "$TMP_KEYS"; then
        if [ "$ADDED" -eq 0 ]; then
            printf "\n# Agregadas automáticamente desde .env.example\n" >> "$ENV_FILE"
        fi
        printf "%s\n" "$line" >> "$ENV_FILE"
        printf "%s\n" "$key" >> "$TMP_KEYS"
        ADDED=$((ADDED + 1))
    fi
done < "$ENV_EXAMPLE"

if [ "$ADDED" -eq 0 ]; then
    echo "  ℹ️  .env ya contiene todas las variables de .env.example."
else
    echo "  ✅ .env sincronizado con .env.example (${ADDED} variables agregadas)."
fi
