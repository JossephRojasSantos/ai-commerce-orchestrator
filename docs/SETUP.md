# Guía de Configuración del Entorno — AI-Commerce Orchestrator

> Complementa el [README.md](../README.md). Cubre prerrequisitos detallados,
> instalación paso a paso con outputs esperados, verificación y troubleshooting.
>
> **Referencia Jira:** [AI-100](https://ai-commerce-orchestrator.atlassian.net/browse/AI-100) | Epic AI-5 | Sprint 0

---

## 1. Prerrequisitos

| Herramienta | Versión mínima | Verificada en este proyecto | Instalación |
|---|---|---|---|
| Docker Engine | ≥ 24.x | 28.5.2 | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| Docker Compose | ≥ 2.20 | 5.1.0 | Incluido con Docker Desktop · `brew install docker-compose` (macOS) |
| Git | ≥ 2.x | — | [git-scm.com/downloads](https://git-scm.com/downloads) |
| GNU Make | ≥ 3.8 | — | `brew install make` (macOS) · preinstalado en Linux |

> **macOS — Colima:** Si usas Colima en lugar de Docker Desktop, el daemon
> debe estar corriendo **antes** de cualquier comando Docker:
>
> ```bash
> colima start
> ```
>
> Verifica que Docker responde: `docker info` (sin error = OK).

---

## 2. Instalación paso a paso

### Paso 1 — Clonar el repositorio

```bash
git clone <URL-del-repositorio>
cd ai-commerce-orchestrator
```

Output esperado:

```
Cloning into 'ai-commerce-orchestrator'...
remote: Enumerating objects: ...
```

### Paso 2 — Configurar variables de entorno

```bash
cp .env.example .env
```

Abre `.env` y edita al menos:

| Variable | Descripción | Ejemplo |
|---|---|---|
| `DB_PASSWORD` | Contraseña de PostgreSQL | `mi_password_seguro` |
| `LLM_API_KEY` | API Key de OpenAI | `sk-...` |

> Las demás variables tienen valores por defecto válidos para desarrollo local.
> **No commitees** el archivo `.env` — está en `.gitignore`.

Output esperado: ninguno — el comando no produce salida si se ejecuta correctamente.

### Paso 3 — Validar configuración

```bash
make setup
```

Output esperado:

```
🔧 Configurando entorno...
  ℹ️  .env ya existe, no se sobreescribe.
✅ Todas las variables de entorno están configuradas.
```

Si aparece `❌ Variables faltantes`, revisa la sección [Troubleshooting](#4-troubleshooting).

### Paso 4 — Levantar los servicios

```bash
make up
```

Output esperado (puede tomar 1-2 min la primera vez mientras descarga imágenes):

```
✅ Servicios iniciados en background.
```

### Paso 5 — Verificar que los servicios están saludables

```bash
docker compose -f infra/docker-compose.yml ps
```

Output esperado — los 3 servicios deben aparecer como `healthy`:

```
NAME                 IMAGE                COMMAND              STATUS
infra-backend-1      python:3.11-slim     "python -m http..."  Up (healthy)
infra-db-1           postgres:15-alpine   "docker-entryp..."   Up (healthy)
infra-redis-1        redis:7-alpine       "docker-entryp..."   Up (healthy)
```

> Si algún servicio aparece como `starting` espera 30 segundos y repite el comando.

---

## 3. Verificación del entorno

Ejecuta los tres comandos siguientes. Cada uno debe devolver el output indicado.

**Backend responde:**

```bash
curl -s http://localhost:8000
```

Output esperado: cualquier respuesta HTTP (código 200 o página HTML del servidor placeholder).

**PostgreSQL acepta conexiones:**

```bash
docker compose -f infra/docker-compose.yml exec db pg_isready -U postgres
```

Output esperado:

```
localhost:5432 - accepting connections
```

**Redis responde:**

```bash
docker compose -f infra/docker-compose.yml exec redis redis-cli ping
```

Output esperado:

```
PONG
```

Si los tres comandos dan el output esperado, el entorno está correctamente configurado.

---

## 4. Troubleshooting

### Problema: Cannot connect to the Docker daemon

**Síntoma:** `docker: Cannot connect to the Docker daemon at unix:///...`

**Causa:** El daemon de Docker no está corriendo (frecuente en macOS con Colima).

**Solución:**

```bash
colima start          # macOS con Colima
# o
open -a Docker        # macOS con Docker Desktop
```

Verifica: `docker info` no debe mostrar errores.

---

### Problema: Puerto ya en uso

**Síntoma:** `Error starting userland proxy: listen tcp 0.0.0.0:5432: bind: address already in use`

**Causa:** Otro proceso (PostgreSQL local, Redis local, etc.) ocupa el puerto.

**Solución:** Cambia el puerto en `.env`:

```bash
# Ejemplo: cambiar puerto de PostgreSQL a 5433
DB_PORT=5433
```

Reinicia: `make restart`

---

### Problema: Variables faltantes en `.env`

**Síntoma:** `make setup` muestra `❌ Variables faltantes en .env:`

**Causa:** El archivo `.env` no tiene todas las variables requeridas.

**Solución:** Compara tu `.env` con `.env.example` y agrega las variables faltantes.

```bash
diff .env.example .env
```

---

### Problema: Imagen no se descarga / error de pull

**Síntoma:** `Error response from daemon: pull access denied` o timeout al bajar imágenes.

**Causa:** Sin conexión a internet o registro inaccesible.

**Nota:** Todas las imágenes del proyecto (`python:3.11-slim`, `postgres:15-alpine`, `redis:7-alpine`)
son multi-arquitectura y compatibles con ARM64 (Apple Silicon). Si el problema persiste,
verifica tu conexión y que Docker Hub sea accesible.

---

## Comandos rápidos

Para la referencia completa de comandos de desarrollo ver el [README.md](../README.md).
