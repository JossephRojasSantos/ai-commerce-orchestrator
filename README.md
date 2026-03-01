# AI-Commerce Orchestrator

Solución de comercio electrónico aumentada con agentes de IA — Proyecto de Grado, Maestría.

## Estructura del proyecto

```
ai-commerce-orchestrator/
├── backend/        # Servicio backend inteligente (API + agentes)
├── infra/          # Infraestructura Docker (docker-compose.yml)
├── docs/           # Documentación técnica (SETUP.md, ADRs)
├── scripts/        # Scripts de utilidad (check-env.sh)
├── .env.example    # Variables de entorno de referencia
├── .gitignore
├── .editorconfig
└── Makefile        # Comandos de desarrollo
```

## Inicio rápido

```bash
# 1. Clonar el repositorio
git clone <repo-url>
cd ai-commerce-orchestrator

# 2. Configurar entorno
make setup       # Copia .env.example → .env y valida variables

# 3. Levantar servicios
make up          # Inicia backend, DB y Redis en Docker

# 4. Ver logs
make logs
```

Consulta [`docs/SETUP.md`](docs/SETUP.md) para la guía completa de instalación.

## Comandos disponibles

| Comando | Descripción |
|---------|-------------|
| `make setup` | Prepara entorno local |
| `make up` | Levanta todos los servicios |
| `make down` | Detiene los servicios |
| `make restart` | Reinicia servicios |
| `make logs` | Logs en tiempo real |
| `make lint` | Ejecuta linter |
| `make test` | Ejecuta tests |
| `make clean` | Elimina contenedores y volúmenes |

## Requisitos

- Docker Engine ≥ 24.x
- Docker Compose ≥ 2.20
- Git ≥ 2.x
- GNU Make

## Jira

- Epic: [AI-5](https://ai-commerce-orchestrator.atlassian.net/browse/AI-5) — Infraestructura local y entorno de desarrollo
- Historia: [AI-15](https://ai-commerce-orchestrator.atlassian.net/browse/AI-15) — Configurar entorno local con Docker
