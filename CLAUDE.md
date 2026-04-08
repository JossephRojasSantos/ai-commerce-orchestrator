# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All development commands run through Make, which wraps Docker Compose commands targeting `infra/docker-compose.yml`.

```bash
make setup    # Sync .env with .env.example and validate required variables
make up       # Start all services in background (--build rebuilds images)
make down     # Stop and remove containers
make restart  # down + up
make logs     # Stream logs from all running services
make lint     # Run flake8 (max-line-length=120) inside Docker
make test     # Run pytest -v inside Docker
make clean    # Remove containers, volumes, and orphans (full reset)
```

First-time setup:
```bash
make setup   # generates .env — edit LLM_API_KEY and DB_PASSWORD before continuing
make up
```

Run lint or tests without starting the full stack:
```bash
docker compose -f infra/docker-compose.yml run --rm backend sh -c "pip install flake8 --quiet && flake8 . --max-line-length=120"
docker compose -f infra/docker-compose.yml run --rm backend sh -c "pip install pytest --quiet && pytest -v tests/path/to/test_file.py"
```

## Architecture

Monorepo with four containerized services orchestrated via Docker Compose:

- **backend** — Python 3.11-slim, port 8000 (configurable via `BACKEND_PORT`). Currently a placeholder; FastAPI + Uvicorn will be implemented here.
- **db** — PostgreSQL 16-alpine, port 5432. Persisted via `ai-db-data` volume.
- **redis** — Redis 7-alpine, port 6379. AOF persistence enabled. Used for caching and Celery task queues.
- **rabbitmq** — RabbitMQ 3-management-alpine, ports 5672/15672. Persisted via `ai-rabbitmq-data` volume.

Services use health checks and `depends_on: condition: service_healthy` — the backend currently waits for db and redis; RabbitMQ starts independently.

All inter-service communication uses Docker network `ai-network`. Internal hostnames (`db`, `redis`) match the `.env` defaults (`DB_HOST=db`, `REDIS_HOST=redis`).

## Environment

Copy `.env.example` to `.env` (done by `make setup`). Required variables validated by `scripts/check-env.sh`:

| Variable | Description |
|---|---|
| DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD | PostgreSQL connection |
| REDIS_HOST / REDIS_PORT | Redis connection |
| RABBITMQ_HOST / RABBITMQ_PORT / RABBITMQ_MGMT_PORT / RABBITMQ_USER / RABBITMQ_PASS | RabbitMQ connection and management UI access |
| LLM_API_KEY | OpenAI API key (gpt-4o-mini) |

`.env` is git-ignored. Never commit it.

## Platform Notes

The project runs on **Apple Silicon (ARM64)** via **Colima** (not Docker Desktop). All images use `-alpine` or `-slim` variants confirmed ARM64-compatible. If switching to x86, no changes needed — images are multi-arch.

## Project Structure

```
ai-commerce-orchestrator/
├── backend/          # Python backend service (FastAPI — to be implemented)
├── infra/
│   ├── docker/       # Dockerfiles and nginx configs (to be added)
│   └── docker-compose.yml
├── docs/             # Technical documentation (setup guides and plans)
├── scripts/
│   ├── sync-env.sh   # Adds missing keys to .env from .env.example
│   ├── check-env.sh  # Validates required .env variables; exits 1 on missing vars
│   └── smoke-test.sh # Verifies DB/Redis/RabbitMQ connectivity from host
├── .env.example      # Environment variable template
└── Makefile
```

## Output Rules (Claude Code)

> Fuente completa: `../../../.claude/rules/general.md`

1. **Código:** solo `git diff` mínimo + comandos. No pegar archivos completos.
2. **Docs:** solo patch de la sección afectada. Máx 300 palabras, 10 bullets, 1 ejemplo + 1 error.
3. **Explicaciones:** máx 5 bullets si son necesarias. Sin "thinking out loud".
4. **Si falta info:** máx 3 preguntas y parar.
5. **Tablas:** máx 10 filas. **Listas:** máx 10 bullets.

## Jira Context

This repository implements **Epic AI-5** (Infrastructure and Development Environment). Active sprint: SCRUM Sprint 0. Stories follow the pattern `AI-NNN`. Implementation plans and acceptance criteria live in `../Epic_AI-5/`.
