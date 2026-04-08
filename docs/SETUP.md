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

> La URL del repositorio se encuentra en la página del proyecto en GitHub.

Output esperado:

```
Cloning into 'ai-commerce-orchestrator'...
remote: Enumerating objects: ...
```

### Paso 2 — Configurar variables de entorno

`make setup` crea `.env` automáticamente desde `.env.example` si no existe.
Edita el archivo `.env` y completa al menos:

| Variable | Descripción | Ejemplo |
|---|---|---|
| `DB_PASSWORD` | Contraseña de PostgreSQL | `mi_password_seguro` |
| `LLM_API_KEY` | API Key de OpenAI | `sk-...` |

> Las demás variables (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `REDIS_HOST`, `REDIS_PORT`)
> tienen valores por defecto válidos para desarrollo local en `.env.example`.
> **No commitees** el archivo `.env` — está en `.gitignore`.

Output esperado: ninguno — es solo edición manual del archivo `.env`.

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
🚀 Levantando servicios...
  ✅ Servicios corriendo. Verifica con: docker ps
```

### Paso 5 — Verificar que los servicios están saludables

```bash
docker compose -f infra/docker-compose.yml ps
```

Output esperado — los 4 servicios deben aparecer como `healthy`:

```
NAME          IMAGE                COMMAND                 STATUS
ai-backend    python:3.11-slim     "python -m http..."     Up (healthy)
ai-db         postgres:16-alpine   "docker-entrypoint…"    Up (healthy)
ai-redis      redis:7-alpine       "docker-entrypoint…"    Up (healthy)
ai-rabbitmq   rabbitmq:3-manag...  "docker-entrypoint…"    Up (healthy)
```

> Si algún servicio aparece como `starting` espera 30 segundos y repite el comando.

---

## 3. Verificación del entorno

Ejecuta los cuatro comandos siguientes. Cada uno debe devolver el output indicado.

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

**RabbitMQ responde:**

```bash
docker compose -f infra/docker-compose.yml exec rabbitmq rabbitmq-diagnostics ping
```

Output esperado:

```
Ping succeeded
```

Si las cuatro verificaciones dan el output esperado, el entorno está correctamente configurado.
Si alguno falla, revisa la sección [Troubleshooting](#4-troubleshooting) o ejecuta `make logs` para ver los logs de los servicios.

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
# O cambiar el puerto de Redis
REDIS_PORT=6380
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

**Nota:** Todas las imágenes del proyecto (`python:3.11-slim`, `postgres:16-alpine`, `redis:7-alpine`, `rabbitmq:3-management-alpine`)
son multi-arquitectura y compatibles con ARM64 (Apple Silicon). Si el problema persiste,
verifica tu conexión y que Docker Hub sea accesible.

---

## 5. Servicios adicionales (AI-16)

### Puertos expuestos

| Servicio | Puerto host | Puerto contenedor | Variable |
|----------|------------|-------------------|----------|
| backend | 8000 | 8000 | `BACKEND_PORT` |
| db (PostgreSQL 16) | 5432 | 5432 | `DB_PORT` |
| redis | 6379 | 6379 | `REDIS_PORT` |
| rabbitmq (AMQP) | 5672 | 5672 | `RABBITMQ_PORT` |
| rabbitmq (Management UI) | 15672 | 15672 | `RABBITMQ_MGMT_PORT` |

### RabbitMQ Management UI

Disponible en http://localhost:15672 una vez levantado `docker compose up rabbitmq`.

Credenciales por defecto: usuario `guest` / contraseña `guest` (cambiar en `.env` para producción).

### Smoke test

Verificar conectividad de todos los servicios:

```bash
bash scripts/smoke-test.sh
```

Salida esperada: `✅ 4 pasaron | ❌ 0 fallaron`.

---

## Comandos rápidos

Para la referencia completa de comandos de desarrollo ver el [README.md](../README.md).

---

## 6. Tienda WooCommerce en Hostinger (AI-17)

| Componente | Detalle |
|-----------|---------|
| URL tienda | `https://tiendamagica.shop` |
| WP Admin | `https://tiendamagica.shop/wp-admin` |
| API base | `https://tiendamagica.shop/wp-json/wc/v3` |
| PHP | 8.3.27 |
| SSL | Let's Encrypt (expira Jun 2026, renovación automática) |
| Backups | Diarios (hPanel → Backups) |
| Hosting | Business Web Hosting, usuario `u384499485` |

### Variables de entorno requeridas

```bash
WOOCOMMERCE_API_URL=https://tiendamagica.shop/wp-json/wc/v3
WOOCOMMERCE_CONSUMER_KEY=ck_...       # ver .env (no en Git)
WOOCOMMERCE_CONSUMER_SECRET=cs_...   # ver .env (no en Git)
```

### Verificar conectividad

```bash
source .env
curl -sI https://tiendamagica.shop | head -1
# HTTP/2 200

curl -u "$WOOCOMMERCE_CONSUMER_KEY:$WOOCOMMERCE_CONSUMER_SECRET" \
  "$WOOCOMMERCE_API_URL/products" | python3 -m json.tool | head -5
# JSON con productos
```
