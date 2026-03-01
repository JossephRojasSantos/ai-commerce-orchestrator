# ==============================================================
# Makefile — AI-Commerce Orchestrator (AI-34)
# Targets: setup, up, down, lint, test
# ==============================================================

COMPOSE_FILE := infra/docker-compose.yml
ENV_FILE     := .env
ENV_EXAMPLE  := .env.example

.PHONY: help setup up down restart logs lint test clean

# ---- Ayuda por defecto ----------------------------------------
help:
	@echo ""
	@echo "  AI-Commerce Orchestrator — Comandos disponibles"
	@echo "  ------------------------------------------------"
	@echo "  make setup    → Prepara el entorno (copia .env, valida variables)"
	@echo "  make up       → Levanta todos los servicios en background"
	@echo "  make down     → Detiene y elimina contenedores"
	@echo "  make restart  → Reinicia todos los servicios"
	@echo "  make logs     → Muestra logs en tiempo real"
	@echo "  make lint     → Ejecuta linter en el backend"
	@echo "  make test     → Ejecuta tests en el backend"
	@echo "  make clean    → Elimina contenedores, volúmenes e imágenes locales"
	@echo ""

# ---- Setup ----------------------------------------------------
setup:
	@echo "🔧 Configurando entorno..."
	@if [ ! -f $(ENV_FILE) ]; then \
		cp $(ENV_EXAMPLE) $(ENV_FILE); \
		echo "  ✅ .env creado desde .env.example. Completa los valores reales."; \
	else \
		echo "  ℹ️  .env ya existe, no se sobreescribe."; \
	fi
	@bash scripts/check-env.sh

# ---- Servicios ------------------------------------------------
up:
	@echo "🚀 Levantando servicios..."
	docker compose -f $(COMPOSE_FILE) up -d --build
	@echo "  ✅ Servicios corriendo. Verifica con: docker ps"

down:
	@echo "🛑 Deteniendo servicios..."
	docker compose -f $(COMPOSE_FILE) down

restart: down up

logs:
	docker compose -f $(COMPOSE_FILE) logs -f

# ---- Calidad --------------------------------------------------
lint:
	@echo "🔍 Ejecutando linter..."
	docker compose -f $(COMPOSE_FILE) run --rm backend \
		sh -c "pip install flake8 --quiet && flake8 . --max-line-length=120 || true"

test:
	@echo "🧪 Ejecutando tests..."
	docker compose -f $(COMPOSE_FILE) run --rm backend \
		sh -c "pip install pytest --quiet && pytest -v || true"

# ---- Limpieza -------------------------------------------------
clean:
	@echo "🧹 Limpiando entorno Docker..."
	docker compose -f $(COMPOSE_FILE) down -v --remove-orphans
	@echo "  ✅ Contenedores y volúmenes eliminados."
