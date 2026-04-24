# ==============================================================
# Makefile — AI-Commerce Orchestrator (AI-34)
# Targets: setup, up, down, lint, test
# ==============================================================

COMPOSE_FILE := infra/docker-compose.yml
ENV_FILE     := .env
ENV_EXAMPLE  := .env.example

.PHONY: help setup up down restart logs lint test cli-build cli-build-local cli-test cli-lint cli-clean clean

# ---- Ayuda por defecto ----------------------------------------
help:
	@echo ""
	@echo "  AI-Commerce Orchestrator — Comandos disponibles"
	@echo "  ------------------------------------------------"
	@echo "  make setup    → Prepara el entorno (sincroniza .env, valida variables)"
	@echo "  make up       → Levanta todos los servicios en background"
	@echo "  make down     → Detiene y elimina contenedores"
	@echo "  make restart  → Reinicia todos los servicios"
	@echo "  make logs     → Muestra logs en tiempo real"
	@echo "  make lint     → Ejecuta linter en el backend"
	@echo "  make test     → Ejecuta tests en el backend"
	@echo "  make cli-build→ Compila 3 binaries del CLI (darwin-arm64, darwin-amd64, linux-amd64)"
	@echo "  make cli-build-local → Compila binary local del CLI"
	@echo "  make cli-test → Ejecuta tests del CLI en Go"
	@echo "  make cli-lint → Ejecuta lint del CLI en Go"
	@echo "  make cli-clean→ Elimina binarios y cobertura del CLI"
	@echo "  make clean    → Elimina contenedores, volúmenes e imágenes locales"
	@echo ""

# ---- Setup ----------------------------------------------------
setup:
	@echo "🔧 Configurando entorno..."
	@bash scripts/sync-env.sh
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
		sh -c "pip install flake8 --quiet && flake8 . --max-line-length=120"

test:
	@echo "🧪 Ejecutando tests..."
	docker compose -f $(COMPOSE_FILE) run --rm \
		-v "$(PWD)/backend/app:/app/app" \
		-v "$(PWD)/backend/tests:/app/tests" \
		backend \
		sh -c "pytest -v tests/ --cov=app --cov-report=term-missing"

# ---- CLI (Go) --------------------------------------------------
cli-build:
	@$(MAKE) -C cli build-all

cli-build-local:
	@$(MAKE) -C cli build

cli-test:
	@$(MAKE) -C cli test

cli-lint:
	@$(MAKE) -C cli lint

cli-clean:
	@$(MAKE) -C cli clean

# ---- Limpieza -------------------------------------------------
clean:
	@echo "🧹 Limpiando entorno Docker..."
	docker compose -f $(COMPOSE_FILE) down -v --remove-orphans
	@echo "  ✅ Contenedores y volúmenes eliminados."
