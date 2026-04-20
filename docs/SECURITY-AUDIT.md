# Security Audit — AI Commerce Orchestrator

**Fecha:** 2026-04-09
**Alcance:** Backend FastAPI · Infraestructura Docker · WordPress mu-plugins · Go CLI · Cliente WooCommerce
**Método:** Análisis estático de código (4 agentes paralelos, read-only)

---

## Resumen ejecutivo

| Severidad | Cantidad |
|-----------|----------|
| CRÍTICO   | 4        |
| ALTO      | 7        |
| MEDIO     | 11       |
| BAJO / INFO | 8      |
| **Total** | **30**   |

---

## CRÍTICOS

### C1 — Secretos reales en `.env`
**Archivo:** `.env` (local, no trackeado en git)

El archivo contiene credenciales reales activas:
- `WOOCOMMERCE_CONSUMER_KEY` / `WOOCOMMERCE_CONSUMER_SECRET` — OAuth WooCommerce
- `WP_ADMIN_KEY` — Application Password de WordPress Admin
- `MP_PUBLIC_KEY` / `MP_TOKEN` — MercadoPago (entorno TEST)
- `AT_API_TOKEN` — token Atlassian con acceso a toda la instancia Jira/Confluence

Aunque no está trackeado en git, cualquier backup, sync a nube o acceso al filesystem lo expone.

**Acción:** Rotar todas las credenciales listadas. Evaluar uso de secret manager (Vault, 1Password Secrets Automation, AWS SSM).

---

### C2 — `.env.bak` con secretos en disco
**Archivo:** `.env.bak`

Copia exacta del `.env` con todas las credenciales reales. El `.gitignore` lo excluye via `*.bak` (frágil), pero su existencia en disco es un riesgo de fuga por backups o sync.

**Acción:**
```bash
rm .env.bak
# Añadir línea explícita al .gitignore:
echo ".env.bak" >> .gitignore
```

---

### C3 — `GET /chat/history/{session_id}` sin autenticación
**Archivo:** `backend/app/routers/chat.py:38`

El endpoint no requiere ningún token. Cualquier cliente que conozca o adivine un `session_id` (UUID v4) puede leer el historial completo de conversación de otro usuario, incluyendo su contenido e IP.

**Acción:** Requerir JWT o API-key. Validar que el `session_id` del token coincida con el parámetro de ruta antes de consultar.

---

### C4 — `GET /orders?customer=` sin autenticación
**Archivo:** `backend/app/routers/orders.py`

Todos los endpoints de `/products` y `/orders` son completamente públicos. `GET /orders?customer=123` devuelve los pedidos de cualquier `customer_id` sin verificar identidad del solicitante.

**Acción:** Añadir `Depends(verify_token)` en los routers. Para `/orders`, verificar que `customer_id == token.sub`.

---

## ALTOS

### A1 — Rate limit bypasseable por `session_id`
**Archivo:** `backend/app/services/chat.py:60`

La clave Redis de rate limit es `ratelimit:chat:{req.session_id}`. El `session_id` llega del cliente en el body sin autenticación. Un atacante puede usar un UUID nuevo en cada request y nunca alcanza el límite de 30/min.

**Acción:** Usar IP como clave primaria: `ratelimit:chat:{user_ip}` o combinación `{user_ip}:{session_id}`.

---

### A2 — Ownership de sesión no verificado
**Archivo:** `backend/app/routers/chat.py`, `backend/app/services/chat.py:71`

`get_or_create_conversation` acepta cualquier `session_id` del cliente sin verificar ownership. Un atacante con un UUID ajeno puede adjuntar mensajes a conversaciones de otros usuarios o leer su historial.

**Acción:** El `session_id` debe generarse y firmarse en el servidor (claim de JWT), nunca provenir libremente del cliente.

---

### A3 — PostgreSQL expuesto en `0.0.0.0:5432`
**Archivo:** `infra/docker-compose.yml:57`

```yaml
ports:
  - "${DB_PORT:-5432}:5432"   # expuesto en todas las interfaces
```

En un VPS o CI con firewall permisivo, la DB es accesible desde la red.

**Acción:**
```yaml
ports:
  - "127.0.0.1:${DB_PORT:-5432}:5432"
```

---

### A4 — Redis sin auth expuesto en `0.0.0.0:6379`
**Archivo:** `infra/docker-compose.yml:81`

Redis sin `requirepass` queda completamente abierto en todas las interfaces.

**Acción:**
```yaml
ports:
  - "127.0.0.1:${REDIS_PORT:-6379}:6379"
command: redis-server --requirepass ${REDIS_PASSWORD}
```

---

### A5 — RabbitMQ Management UI en `0.0.0.0:15672` con `guest/guest`
**Archivo:** `infra/docker-compose.yml:104`

El panel de administración web queda accesible externamente con las credenciales universalmente conocidas `guest/guest` como fallback.

**Acción:**
```yaml
ports:
  - "127.0.0.1:${RABBITMQ_MGMT_PORT:-15672}:15672"
# Eliminar defaults :-guest en RABBITMQ_DEFAULT_USER / RABBITMQ_DEFAULT_PASS
```

---

### A6 — Sin rate limit en `/products` y `/orders`
**Archivos:** `backend/app/routers/products.py`, `backend/app/routers/orders.py`

Solo `/chat` tiene rate limiting. Los endpoints de productos y órdenes pueden ser scrapeados o forzados sin restricción.

**Acción:** Añadir middleware global de rate limit (e.g. `slowapi`) o dependencia por router.

---

### A7 — OAuth1 double-encoding en `signing_key`
**Archivo:** `backend/app/clients/woocommerce.py:59`

```python
signing_key = f"{quote(settings.WC_CONSUMER_SECRET, safe='')}&"
```

Si el secret contiene caracteres especiales (`%`, `&`, `=`), `quote()` produce double-encoding. La firma resultante puede ser incorrecta o predecible con secrets complejos.

**Acción:** Construir la signing key sin `quote()` en el secret o usar la librería oficial `woocommerce`:
```python
signing_key = f"{settings.WC_CONSUMER_SECRET}&"  # sin quote para two-legged OAuth
```

---

## MEDIOS

### M1 — `DATABASE_URL` con password hardcodeada por defecto
**Archivo:** `backend/app/config.py:7`

```python
DATABASE_URL: str = "postgresql+asyncpg://postgres:change_me@db:5432/ai_commerce"
```

Si `.env` no existe, la app arranca con contraseña pública.

**Acción:** Usar `DATABASE_URL: str = Field(...)` sin default, o validar en startup que no sea el valor por defecto.

---

### M2 — CORS demasiado permisivo
**Archivo:** `backend/app/main.py:28`

```python
allow_methods=["*"], allow_headers=["*"]
```

**Acción:** Listar explícitamente solo los métodos (`GET`, `POST`) y headers necesarios (`Content-Type`, `Authorization`).

---

### M3 — Contenedor backend corre como root
**Archivo:** `infra/docker/Dockerfile.backend`

No hay directiva `USER`. Uvicorn corre como root dentro del contenedor.

**Acción:** Añadir antes del `CMD`:
```dockerfile
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser
```

---

### M4 — Tests incluidos en imagen de producción
**Archivo:** `infra/docker/Dockerfile.backend:17`

`pytest`, `fakeredis`, `respx` y el directorio `tests/` se copian a la imagen final. Aumenta superficie de ataque y tamaño de imagen.

**Acción:** Usar target `test` separado en el multi-stage Dockerfile. No copiar `backend/tests` en la imagen `final`.

---

### M5 — `check-env.sh` sin `pipefail` ni `nounset`
**Archivo:** `scripts/check-env.sh:5`

```bash
set -e   # falta -u -o pipefail
```

**Acción:** `set -euo pipefail` (como ya hacen correctamente `sync-env.sh` y `smoke-test.sh`).

---

### M6 — `eval "$cmd"` con variables de entorno sin sanitizar
**Archivo:** `scripts/smoke-test.sh:35`

Los valores de `$cmd` se construyen con `${DB_HOST}`, `${RABBITMQ_USER}`, etc. Si alguna variable contiene `;`, `$()` u otros metacaracteres de shell, `eval` los ejecutaría.

**Acción:** Reemplazar `eval "$cmd"` por arrays de comandos o funciones bash directas.

---

### M7 — Retry sin jitter (thundering herd)
**Archivo:** `backend/app/core/retry.py:13`

```python
wait_exponential(multiplier=0.5, max=4)  # sin jitter
```

Si N workers reciben 5xx simultáneamente, todos reintentan al mismo tiempo en cada backoff.

**Acción:** Usar `wait_exponential_jitter()` de tenacity.

---

### M8 — `status` de órdenes sin whitelist
**Archivo:** `backend/app/routers/orders.py:17`

```python
status: str | None = Query(None)  # acepta cualquier string
```

El valor se pasa directamente a WooCommerce sin validación.

**Acción:**
```python
from typing import Literal
status: Literal["pending","processing","on-hold","completed","cancelled","refunded","failed"] | None = Query(None)
```

---

### M9 — `apiBase` del widget modificable desde scripts externos
**Archivo:** `tienda-magica/wp-content/mu-plugins/chat-widget/src/api.js:2`

```js
const API_BASE = window.TM_CHAT_CONFIG?.apiBase || 'http://localhost:8000';
```

Un plugin comprometido puede sobreescribir `TM_CHAT_CONFIG.apiBase` antes de que cargue el widget, redirigiendo todas las peticiones del chat a un servidor malicioso.

**Acción:** Validar en `api.js` que `apiBase` empieza con `https://tiendamagica.shop` antes de usarla.

---

### M10 — Doble implementación del widget activa
**Archivos:** `chat-widget.js` (legacy WebSocket) + `chat-widget/src/widget.js` (Shadow DOM)

Si ambos se cargan simultáneamente, compiten por el DOM y abren dos conexiones con el backend.

**Acción:** Verificar que `chat-widget.js` no está encolado en `wp_enqueue_scripts`. Si es código legacy, eliminarlo.

---

### M11 — CLI `--url` acepta `http://` sin advertencia
**Archivo:** `cli/cmd/ingest.go:34`

El header `X-Admin-Key` se envía aunque la URL destino sea `http://` (sin TLS).

**Acción:** Validar que `--url` empiece con `https://` o emitir warning visible antes de enviar credenciales.

---

## BAJOS / INFO

| # | Hallazgo | Archivo | Acción |
|---|----------|---------|--------|
| B1 | Cache keys con MD5 sin namespace de tenant | `core/cache.py` | Prefijo con `STORE_ID`, usar sha256 |
| B2 | `bloginfo('name')` sin escape explícito en atributos | `footer.php:23`, `nav.php:49` | Usar `esc_attr(get_bloginfo('name'))` |
| B3 | `$badge_html` con `phpcs:ignore` | `product-grid.php:66` | Reemplazar con `wp_kses()` |
| B4 | Versión del plugin expuesta en `TM_CHAT_CONFIG` | `chat-widget.php:42` | Eliminar campo `version` del frontend |
| B5 | WC credentials vacías no fallan en startup | `config.py:14` | Validar con `@model_validator` en startup |
| B6 | Logs de red pueden filtrar URLs con params OAuth | `clients/woocommerce.py:81` | Sanitizar `e.request.url` antes de loguear |
| B7 | `--env-file` en CLI acepta paths arbitrarios | `cli/internal/checker/env.go:12` | Validar que el path sea relativo al CWD |
| B8 | `oauth_nonce` con `uuid4` sin documentar | `clients/woocommerce.py:45` | Añadir comentario que justifique el uso de `os.urandom` |

---

## Plan de acción priorizado

### Hoy
```bash
# Rotar credenciales (AT_API_TOKEN, WP_ADMIN_KEY, WC keys, MP tokens)
# Eliminar .env.bak
rm .env.bak
echo ".env.bak" >> .gitignore
```

### Antes de exposición pública del backend
1. Auth en `/chat/history`, `/orders`, `/products` (C3, C4)
2. Rate limit por IP en `/chat` (A1)
3. Bindear puertos Docker a `127.0.0.1` (A3, A4, A5)
4. Cambiar credenciales RabbitMQ de `guest/guest` (A5)
5. Fix OAuth `signing_key` en `woocommerce.py` (A7)

### Próximo sprint
6. `USER appuser` en Dockerfile + separar imagen de tests (M3, M4)
7. `wait_exponential_jitter()` en retry policy (M7)
8. Whitelist `status` como `Literal[...]` en Pydantic (M8)
9. Validar `apiBase` contra dominio permitido en `api.js` (M9)
10. Eliminar `chat-widget.js` legacy (M10)
11. `set -euo pipefail` en `check-env.sh` (M5)
12. Eliminar `eval` en `smoke-test.sh` (M6)

---

## Aspectos correctos detectados

- `.env` y `.env.bak` **no trackeados en git** ✅
- `.dockerignore` excluye correctamente `.env*` ✅
- Imágenes Docker con versiones fijas (no `latest`) ✅
- Outputs PHP con `esc_html()`, `esc_attr()`, `esc_url()` consistentes ✅
- Widget moderno usa **Shadow DOM** (aísla CSS, limita superficie XSS) ✅
- `appendMessage()` usa `textContent` (no `innerHTML`) con datos del servidor ✅
- `ABSPATH` guard presente en todos los archivos PHP ✅
- TLS habilitado por defecto en `httpx.AsyncClient` y Go `http.Client` ✅
- `oauth_nonce` usa `uuid4` (criptográficamente seguro) ✅
- Sin CVEs conocidos en dependencias Python y Go (a 2026-04-09) ✅
- `init.sql` sin credenciales hardcodeadas ni usuarios con privilegios excesivos ✅
- Red Docker `ai-network` con driver bridge aísla servicios ✅
