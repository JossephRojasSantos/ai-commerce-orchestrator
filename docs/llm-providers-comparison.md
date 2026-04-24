# Comparativa de enfoques de integración de proveedores LLM

**Proyecto:** AI Commerce Orchestrator (Tienda Mágica)
**Backend:** FastAPI + httpx
**Agentes:** Chat · Router/Orquestador · WhatsApp
**Autor:** Equipo de desarrollo — Tienda Mágica
**Última revisión:** 2026-04-22
**Estado:** ✅ Implementado en rama `009-inner-pages-design` — pasos 2–3 del roadmap completados.

---

## 1. Introducción

El **AI Commerce Orchestrator** es el backend en FastAPI que sirve de cerebro conversacional para la tienda electrónica **Tienda Mágica**. La arquitectura actual expone tres agentes especializados construidos sobre un mismo núcleo LLM:

1. **Chat agent** — Atiende al cliente final dentro del widget web embebido en WordPress. Responde preguntas sobre productos, maneja FAQs, guía en el proceso de compra y mantiene conversación multi-turno.
2. **Router / Orquestador** — Recibe cada mensaje entrante, lo clasifica por intención (consulta de producto, soporte, tracking de pedido, saludo, fuera de dominio) y decide a qué herramienta o agente delegar la tarea. Es un LLM pequeño usado como clasificador.
3. **WhatsApp agent** — Variante del Chat agent adaptada al canal WhatsApp Business API: mensajes más cortos, menos markdown, más uso de emojis y botones interactivos.

Hoy el backend implementa una única ruta de llamada al modelo: un `POST` vía `httpx.AsyncClient` contra un endpoint **OpenAI-compatible** (`/v1/chat/completions`) parametrizado por variables de entorno (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`). Esta solución funcionó durante el MVP porque es simple, sin dependencias pesadas y fácil de testear con mocks. Sin embargo, a medida que el producto crece aparecen tres necesidades que el enfoque actual no cubre bien:

- **Heterogeneidad de modelos por agente.** El Router necesita un modelo barato y rápido (clasificación pura), mientras que el Chat necesita un modelo con mejor razonamiento y seguimiento de instrucciones. Forzar el mismo modelo a ambos roles desperdicia dinero o sacrifica calidad.
- **Resiliencia ante fallos del proveedor.** Si OpenAI, Anthropic o Google tienen una caída parcial (rate-limit, 5xx, degradación regional), el widget queda mudo. Queremos _fallback_ automático entre modelos equivalentes.
- **Observabilidad de costos.** Necesitamos saber cuánto gasta cada agente, por día, por conversación, sin construir nosotros una capa de métricas desde cero.

Este documento compara cuatro enfoques de integración —`httpx` directo actual, **OpenRouter**, **LiteLLM** y **SDKs directos**— contra doce criterios técnicos y económicos, propone una configuración recomendada, calcula proyecciones de costo y entrega un roadmap de migración incremental con los diffs concretos que hay que aplicar al código.

---

## 2. Enfoques de integración

### 2.1 Descripción breve de cada enfoque

- **Actual (httpx directo).** El código en `app/core/llm.py` abre un cliente httpx, construye el payload OpenAI-compatible y hace `POST` contra una única `LLM_BASE_URL`. No hay abstracción de proveedor; si cambiamos de OpenAI a Anthropic, el payload deja de funcionar (Anthropic no expone el mismo esquema).
- **OpenRouter.** [openrouter.ai](https://openrouter.ai) es un **proxy unificado** que expone una API OpenAI-compatible y enruta internamente a más de 300 modelos de OpenAI, Anthropic, Google, Meta, Mistral, DeepSeek, Cohere y otros. Una sola API key, un solo billing, fallbacks declarativos en la petición (`models: [...]`).
- **LiteLLM.** Librería Python (`pip install litellm`) que abstrae más de 100 providers detrás de la función `completion(model="anthropic/claude-...", ...)`. Puede correrse embebida (biblioteca) o como proxy separado. Traduce el payload OpenAI-like al formato nativo de cada proveedor.
- **SDKs directos.** Instalar `openai`, `anthropic`, `google-generativeai`, etc., y escribir un adaptador por proveedor en el backend. Máximo control, máxima superficie de mantenimiento.

### 2.2 Tabla comparativa

| Criterio | Actual (httpx) | OpenRouter | LiteLLM | SDKs directos |
|---|---|---|---|---|
| 1. Cambio de código requerido | — (status quo) | Muy bajo (solo URL + header) | Bajo (importar y usar `completion()`) | Alto (una clase adaptador por proveedor) |
| 2. Una sola API key | Sí (1) | Sí (1) | No (N, una por proveedor) | No (N) |
| 3. Providers/modelos | 1 endpoint | 300+ | 100+ | Los que integres manualmente |
| 4. Fallback automático | No | Sí, declarativo en la petición | Sí, vía `fallbacks=[...]` | Hay que implementarlo |
| 5. Self-hosted / offline | Sí (si el endpoint lo es) | No (servicio gestionado) | Sí (librería local) | Sí |
| 6. Overhead de latencia | 0 ms (baseline) | +20–80 ms (proxy US) | 0 ms (in-process) | 0 ms |
| 7. Markup de precio | 0 % | 0 % en la mayoría de modelos (cobran al mismo precio que el proveedor) | 0 % | 0 % |
| 8. Observabilidad built-in | Nula | Dashboard con uso, costo, latencia por modelo y por key | Logs configurables, integración con Langfuse/Helicone | Nula |
| 9. Streaming | Sí (SSE manual) | Sí | Sí | Sí |
| 10. Dependencias extra | Ninguna | Ninguna (reusa httpx) | `litellm` (~15 MB + transitives) | 1 paquete por proveedor |
| 11. Mantenimiento | Bajo hoy, alto si crece | Muy bajo | Medio (rompe con actualizaciones) | Alto (cada SDK evoluciona) |
| 12. Vendor lock-in | Al endpoint actual | A OpenRouter (mitigado: API OpenAI-compatible) | Mínimo (código portable) | Ninguno, pero coste de migración alto |

### 2.3 Explicación detallada de cada criterio

**1. Cambio de código requerido.** Mide cuántas líneas del backend actual hay que tocar. Importa porque cada migración tiene coste en horas, riesgo de regresión y necesidad de re-testear los tres agentes. Con OpenRouter basta cambiar `LLM_BASE_URL` y añadir un header opcional `HTTP-Referer`; con SDKs directos hay que reescribir la capa `llm.py` como una interfaz con múltiples implementaciones, lo que implica refactorizar tests y fixtures.

**2. Una sola API key vs múltiples.** Tener una sola credencial simplifica rotación, secretos en CI/CD (GitHub Actions, Hostinger), _budget alerts_ y onboarding de nuevos desarrolladores. Con SDKs directos o LiteLLM multi-proveedor hay que gestionar N secrets y N dashboards de facturación, lo cual en un proyecto de tesis con recursos limitados es una fuente de fricción innecesaria.

**3. Providers/modelos soportados.** Define el techo de elección futura. OpenRouter y LiteLLM dan acceso a más de 100 modelos sin escribir código nuevo; esto habilita A/B testing (ej. comparar Claude Haiku vs GPT-4o mini para el Router) sin refactor. El enfoque httpx actual nos ata al esquema OpenAI-compatible: no podemos llamar Claude nativo ni Gemini nativo sin cambiar todo el payload.

**4. Fallback automático entre modelos.** Si el proveedor primario falla (429, 503, timeout), el sistema debe reintentar contra un modelo equivalente antes de propagar el error al widget. OpenRouter acepta en el body `"models": ["openai/gpt-4o-mini", "anthropic/claude-haiku-4-5"]` y hace el fallback en el edge. LiteLLM expone `fallbacks=[...]` en la llamada. Con httpx o SDKs directos hay que implementar el patrón circuit-breaker manualmente (tenacity + lista de modelos), añadiendo 50–100 líneas de código con sus tests.

**5. Funciona offline / self-hosted.** Relevante para entornos air-gapped, demos sin internet y tests de integración. OpenRouter es un servicio SaaS: sin internet no responde. LiteLLM es una librería local y puede apuntar a Ollama/vLLM para correr Llama 3.1 sobre hardware propio. En Tienda Mágica no es un requisito crítico (la tienda vive en Hostinger con internet garantizado), pero sí lo es para CI: los tests del pipeline no deberían depender de la red — de ahí la importancia de mantener un mock.

**6. Overhead de latencia.** El proxy de OpenRouter añade un hop de red. En mediciones publicadas por OpenRouter y validadas por la comunidad, el overhead medio oscila entre 20 y 80 ms según región del cliente (Estados Unidos, Frankfurt o Singapur son los PoPs más cercanos a LatAm). Para un agente conversacional donde la respuesta del modelo tarda 800–2500 ms, 50 ms extra es un 2–5 % y es aceptable. Para el Router, que hace clasificaciones cortas en 200–400 ms, el impacto relativo es mayor (~15 %) pero sigue dentro del presupuesto de latencia del widget (SLA interno: 2 s end-to-end).

**7. Markup de precio.** OpenRouter cobra al mismo precio listado por el proveedor original en la gran mayoría de modelos; monetiza con créditos prepago y un pequeño _spread_ en algunos modelos premium (documentado públicamente en su página de precios). LiteLLM y SDKs directos no cobran markup, pero tampoco dan los servicios añadidos (dashboard, fallback, single-key).

**8. Observabilidad built-in.** OpenRouter entrega de serie un dashboard con gráficas por modelo, por API key y por día, exportable en CSV. Permite crear varias keys (una por agente: `key-chat`, `key-router`, `key-whatsapp`) y obtener automáticamente el desglose de gasto por agente sin escribir código. LiteLLM se integra con Langfuse y Helicone pero requiere configurarlos; httpx y SDKs directos obligan a escribir nuestro propio logger de tokens.

**9. Streaming de respuestas.** Los tres agentes se benefician de SSE: el widget del chat pinta la respuesta token a token y la percepción de velocidad mejora drásticamente. Los cuatro enfoques soportan streaming, pero OpenRouter y LiteLLM lo exponen con la misma API OpenAI-compatible que ya usamos.

**10. Dependencias extra y tamaño.** Cada dependencia añadida al `requirements.txt` es superficie de ataque (CVEs), tiempo de build en Docker y riesgo de incompatibilidad con FastAPI/Pydantic. OpenRouter no añade nada: reusa httpx. LiteLLM añade ~15 MB y arrastra `tokenizers`, `tiktoken` y otras. Los SDKs directos suman ~30–50 MB combinados.

**11. Mantenimiento a largo plazo.** Cuanto más código propio de integración haya, más trabajo de mantenimiento. Los proveedores cambian sus endpoints (Anthropic migró de `/v1/complete` a `/v1/messages`, Google cambió `palm` por `gemini`). OpenRouter absorbe esos cambios; los SDKs directos nos obligan a seguir cada release.

**12. Vendor lock-in.** OpenRouter parece un lock-in, pero como expone OpenAI-compatible, migrar fuera equivale a cambiar `LLM_BASE_URL` — el mismo esfuerzo que nos tomó entrar. LiteLLM minimiza el lock-in al proveedor pero nos ata a la librería. SDKs directos evitan lock-in a proxies a cambio de asumir el lock-in del SDK de cada proveedor.

---

## 3. Modelos disponibles — tabla de precios

Precios públicos de abril de 2026 en USD por **1 millón de tokens**. Los valores pueden variar; consultar el dashboard de OpenRouter para precio vigente.

| Modelo | Provider | Input ($/1M) | Output ($/1M) | Contexto | Velocidad | Ideal para |
|---|---|---|---|---|---|---|
| gpt-4o | OpenAI | 2.50 | 10.00 | 128k | Media | Chat premium, razonamiento complejo |
| gpt-4o-mini | OpenAI | 0.15 | 0.60 | 128k | Alta | Chat general, WhatsApp, buen balance |
| claude-opus-4-7 | Anthropic | 15.00 | 75.00 | 200k | Media-baja | Tareas complejas, análisis de documentos |
| claude-sonnet-4-6 | Anthropic | 3.00 | 15.00 | 200k | Media | Chat premium con contexto largo |
| claude-haiku-4-5 | Anthropic | 0.25 | 1.25 | 200k | Alta | Chat ligero con alta calidad |
| gemini-2.0-flash | Google | 0.10 | 0.40 | 1M | Muy alta | Router, clasificación, alta concurrencia |
| gemini-1.5-flash | Google | 0.075 | 0.30 | 1M | Muy alta | Tareas masivas, tokens baratos |
| gemini-1.5-pro | Google | 1.25 | 5.00 | 2M | Media | Contexto gigantesco, RAG pesado |
| llama-3.1-70b | Meta (via OR) | 0.52 | 0.75 | 128k | Media | Open-source premium, self-host posible |
| llama-3.1-8b | Meta (via OR) | 0.06 | 0.06 | 128k | Alta | Router barato, alta concurrencia |
| deepseek-chat | DeepSeek | 0.14 | 0.28 | 64k | Alta | Chat económico con buen razonamiento |
| mistral-7b | Mistral | 0.07 | 0.07 | 32k | Alta | Backup ultra-barato |

---

## 4. Proyección de costos mensuales

### 4.1 Supuestos base (MVP)

- **Tráfico:** 100 conversaciones por día.
- **Mensajes por conversación:** 10 (ida y vuelta).
- **Tokens por mensaje:** ~500 (prompt del sistema incluido, contexto acumulado del histórico).
- **Total:** 100 × 10 × 500 × 30 días = **15 millones de tokens/mes** repartidos ~40 % input / ~60 % output (las respuestas del asistente tienden a ser más largas que el mensaje del usuario).

De esos 15 M: 6 M input + 9 M output. El Router consume ~15 % del total (un mensaje extra de clasificación por turno del usuario, respuesta corta).

### 4.2 Costo por configuración (15 M tokens/mes)

| Configuración | Chat | Router | Costo mensual estimado |
|---|---|---|---|
| Todo gpt-4o | gpt-4o | gpt-4o | 6 × 2.50 + 9 × 10 = **$105.00** |
| Todo gpt-4o-mini | gpt-4o-mini | gpt-4o-mini | 6 × 0.15 + 9 × 0.60 = **$6.30** |
| Todo gemini-2.0-flash | gemini-2.0-flash | gemini-2.0-flash | 6 × 0.10 + 9 × 0.40 = **$4.20** |
| Todo claude-haiku-4-5 | haiku | haiku | 6 × 0.25 + 9 × 1.25 = **$12.75** |
| **Propuesta recomendada** | gpt-4o-mini | gemini-2.0-flash | Chat 85 %: 5.1 × 0.15 + 7.65 × 0.60 = 5.36 · Router 15 %: 0.9 × 0.10 + 1.35 × 0.40 = 0.63 · **≈ $6.00** |
| Premium mixto | claude-sonnet-4-6 | gemini-2.0-flash | Chat: 5.1 × 3 + 7.65 × 15 = 129.60 · Router: 0.63 · **≈ $130.23** |

### 4.3 Escalado (configuración propuesta: gpt-4o-mini + gemini-2.0-flash)

El costo es aproximadamente lineal con el volumen de conversaciones:

| Escenario | Conv/día | Tokens/mes | Costo/mes | Costo/conv |
|---|---|---|---|---|
| MVP | 100 | 15 M | $6 | $0.002 |
| Crecimiento | 500 | 75 M | $30 | $0.002 |
| Medio | 2 000 | 300 M | $120 | $0.002 |
| Alto | 10 000 | 1 500 M | $600 | $0.002 |

### 4.4 Cómo calcular tu propio escenario

```
tokens_mes     = conv_dia * msg_conv * tokens_msg * 30
input_mes      = tokens_mes * 0.4
output_mes     = tokens_mes * 0.6
costo_chat     = (input_mes * precio_in + output_mes * precio_out) * 0.85 / 1_000_000
costo_router   = (input_mes * 0.10 + output_mes * 0.40) * 0.15 / 1_000_000
costo_total    = costo_chat + costo_router
```

Ajusta el factor 0.85/0.15 según tu distribución real medida desde el dashboard de OpenRouter.

---

## 5. Configuración ideal recomendada

### 5.1 Asignación por agente

| Agente | Modelo | Vía | Razón |
|---|---|---|---|
| **Chat** | `openai/gpt-4o-mini` | OpenRouter | Balance óptimo calidad/precio; buena coherencia multi-turno; soporta tool-calling nativo para acciones de tienda. |
| **Router / Orquestador** | `google/gemini-2.0-flash` | OpenRouter | Tarea de clasificación pura; 4× más barato que gpt-4o-mini; latencia baja (<300 ms); contexto 1M por si añadimos few-shots. |
| **WhatsApp** | `openai/gpt-4o-mini` | OpenRouter | Consistencia tonal con Chat; prompts idénticos con sólo variación de estilo (más corto, más emoji). |

Como **fallback** declarativo por cada agente sugerimos:

- Chat → `anthropic/claude-haiku-4-5` (calidad conversacional similar).
- Router → `meta-llama/llama-3.1-8b-instruct` (clasificación barata).

### 5.2 Diff de implementación

#### `app/config.py`

```diff
  class Settings(BaseSettings):
-     LLM_API_KEY: str = ""
-     LLM_API_BASE: str = "https://api.openai.com/v1"
-     LLM_MODEL: str = "gpt-4o-mini"
-     LLM_TIMEOUT: float = 30.0
+     LLM_API_KEY: str = ""
+     LLM_API_BASE: str = "https://openrouter.ai/api/v1"
+     LLM_MODEL_CHAT: str = "openai/gpt-4o-mini"
+     LLM_MODEL_ROUTER: str = "google/gemini-2.0-flash"
+     LLM_MODEL_WHATSAPP: str = "openai/gpt-4o-mini"
+     LLM_FALLBACK_CHAT: str = "anthropic/claude-haiku-4-5"
+     LLM_FALLBACK_ROUTER: str = "meta-llama/llama-3.1-8b-instruct"
+     LLM_TIMEOUT: float = 30.0
+     OPENROUTER_REFERER: str = "https://tiendamagica.shop"
+     OPENROUTER_APP_NAME: str = "Tienda Magica"
```

#### `app/clients/llm.py`

```diff
- async def chat_complete(messages: list[dict], temperature: float = 0.0) -> str:
+ async def chat_complete(
+     messages: list[dict],
+     model: str | None = None,
+     fallback: str | None = None,
+     temperature: float = 0.0,
+ ) -> str:
+     _model = model or settings.LLM_MODEL_CHAT
+     payload: dict = {"model": _model, "messages": messages, "temperature": temperature}
+     if fallback:
+         payload["models"] = [_model, fallback]
      async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
          resp = await client.post(
              f"{settings.LLM_API_BASE}/chat/completions",
-             headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
-             json={"model": settings.LLM_MODEL, "messages": messages, "temperature": temperature},
+             headers={
+                 "Authorization": f"Bearer {settings.LLM_API_KEY}",
+                 "HTTP-Referer": settings.OPENROUTER_REFERER,
+                 "X-Title": settings.OPENROUTER_APP_NAME,
+                 "X-OR-Prompt-Training": "false",
+             },
+             json=payload,
          )
          resp.raise_for_status()
-         data = resp.json()
-         return data["choices"][0]["message"]["content"]
+         return resp.json()["choices"][0]["message"]["content"]
```

#### `app/services/orchestrator/agents/chat.py`

```diff
+ from app.config import settings
  from app.services.orchestrator.state import ConversationState

- reply = await chat_complete(messages)
+ reply = await chat_complete(
+     messages,
+     model=settings.LLM_MODEL_CHAT,
+     fallback=settings.LLM_FALLBACK_CHAT,
+ )
```

#### `app/services/orchestrator/router.py`

```diff
- raw = await chat_complete(
-     [{"role": "user", "content": _CLASSIFIER_PROMPT.format(text=text)}],
-     temperature=0.0,
- )
+ raw = await chat_complete(
+     [{"role": "user", "content": _CLASSIFIER_PROMPT.format(text=text)}],
+     model=settings.LLM_MODEL_ROUTER,
+     fallback=settings.LLM_FALLBACK_ROUTER,
+     temperature=0.0,
+ )
```

#### `.env.example`

```bash
LLM_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx
LLM_API_BASE=https://openrouter.ai/api/v1
LLM_MODEL_CHAT=openai/gpt-4o-mini
LLM_MODEL_ROUTER=google/gemini-2.0-flash
LLM_MODEL_WHATSAPP=openai/gpt-4o-mini
LLM_FALLBACK_CHAT=anthropic/claude-haiku-4-5
LLM_FALLBACK_ROUTER=meta-llama/llama-3.1-8b-instruct
OPENROUTER_REFERER=https://tiendamagica.shop
OPENROUTER_APP_NAME=Tienda Magica
```

#### Variables de producción (Hostinger)

Crear **tres API keys distintas** en el dashboard de OpenRouter:

- `tm-prod-chat` → usada por el agente Chat.
- `tm-prod-router` → usada por el Router.
- `tm-prod-whatsapp` → usada por WhatsApp.

Esto permite ver el desglose de costos por agente directamente en el dashboard, rotar cada key por separado si se filtra y aplicar budget alerts independientes. Si no quieres tres keys, usa una sola y distingue los agentes por el header `X-Title` diferente por llamada.

---

## 6. Roadmap de migración

| # | Paso | Duración | Riesgo | Estado |
|---|---|---|---|---|
| 1 | Crear cuenta OpenRouter, recargar $20 de crédito, generar 3 keys. | 15 min | Nulo | ⏳ Pendiente |
| 2 | Aplicar diff de `config.py`, `clients/llm.py`, `.env.example`. | 1 h | Bajo | ✅ Hecho |
| 3 | Tests unitarios: mocks de `chat_complete` son call-site — no requirieron cambios (params opcionales con defaults). | — | — | ✅ Hecho |
| 4 | Smoke test local: las tres rutas (`/chat`, `/router`, `/whatsapp`) devuelven 200. | 30 min | Bajo | ⏳ Pendiente |
| 5 | Desplegar a staging, correr suite de regresión con 20 conversaciones de referencia. | 1 h | Medio | ⏳ Pendiente |
| 6 | Comparar calidad del Router (gemini-flash vs modelo actual) con set etiquetado de 100 mensajes. | 2 h | Medio | ⏳ Pendiente |
| 7 | Merge a `main`, deploy a producción en ventana de baja carga. | 30 min | Medio | ⏳ Pendiente |
| 8 | Activar budget alerts en OpenRouter ($50/mes soft, $100/mes hard). | 10 min | Nulo | ⏳ Pendiente |
| 9 | Monitorear 7 días: latencia p95, tasa de error, costo diario. | — | Bajo | ⏳ Pendiente |
| 10 | Retirar el endpoint OpenAI directo de los secrets (cleanup). | 10 min | Nulo | ⏳ Pendiente |

Todos los pasos son reversibles cambiando `LLM_API_BASE` de vuelta al endpoint anterior.

---

## 7. Consideraciones de seguridad y costos

### 7.1 Rate limiting por agente

Aplicar un middleware de FastAPI (`slowapi` o un limitador propio con Redis) con ventanas por IP y por sesión:

- Chat: 30 mensajes / 5 min / sesión.
- WhatsApp: 60 mensajes / 5 min / número.
- Router: no se expone público; lo invoca Chat internamente.

Esto corta ataques de "prompt storm" donde un atacante fuerza miles de llamadas para vaciar los créditos.

### 7.2 Alertas de costo

En el dashboard de OpenRouter, configurar para cada key:

- **Soft alert** al 60 % del presupuesto mensual → email.
- **Hard limit** al 100 % → la key deja de responder (fail-closed).

Adicionalmente, exportar el CSV diario vía cron a un bucket y lanzar alerta si el costo de un día supera 2× el promedio de los últimos 7 días.

### 7.3 Rotación de API keys

Rotar cada 90 días como mínimo, o inmediatamente ante sospecha de filtración. El flujo:

1. Crear nueva key con mismo nombre + sufijo `v2`.
2. Actualizar secret en Hostinger + redeploy.
3. Verificar 15 min que el tráfico fluye en la nueva.
4. Revocar la antigua.

Nunca commitear keys; usar `.env` en local y secrets del proveedor en prod. El `.gitignore` ya excluye `.env` — verificar con `git check-ignore .env`.

### 7.4 Privacidad y logs

**Nunca** loggear en producción el contenido completo de los mensajes ni de las respuestas del modelo. Los mensajes contienen PII (nombre, email, dirección de envío, a veces datos de tarjetas parciales). Reglas:

- Log level INFO → solo IDs, modelo, tokens usados, latencia.
- Log level DEBUG (desactivado en prod) → puede incluir mensajes truncados a 100 caracteres con PII enmascarada.
- OpenRouter permite desactivar el _training_ de proveedores upstream vía el header `X-OR-Prompt-Training: false`. **✅ Ya implementado** en `app/clients/llm.py` — el header se envía en cada request.
- Si se integra con analytics, enviar solo métricas agregadas, nunca texto.

### 7.5 Checklist rápido pre-producción

- [ ] Tres API keys creadas y rotadas en los últimos 90 días.
- [ ] Budget alerts configurados (soft + hard).
- [x] Rate limiting activo en Chat (`CHAT_RATE_LIMIT_PER_MIN`) y WhatsApp (`WA_RATE_LIMIT_PER_HOUR`).
- [x] Prompt-training desactivado — header `X-OR-Prompt-Training: false` en `app/clients/llm.py`.
- [x] Fallback declarativo implementado — `models: [primary, fallback]` en payload vía `chat_complete(fallback=...)`.
- [ ] Fallback probado manualmente (apagar modelo primario en staging y verificar que responde el secundario).
- [x] `.env` fuera del repositorio (`git check-ignore .env`).
- [ ] Logs revisados: sin contenido de mensajes en producción.
- [ ] Documento de runbook: qué hacer si OpenRouter cae por completo (plan B: cambiar `LLM_API_BASE` a endpoint OpenAI directo con key de backup).

---

**Fin del documento.**
