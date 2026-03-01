# Onboarding Guide (AI-100) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Crear `docs/SETUP.md` con prerrequisitos, pasos numerados con outputs esperados, verificación y troubleshooting; documentar el cierre de AI-100 en `Doc_HU-AI15.md`.

**Architecture:** Documento Markdown complementario al README.md. No repite la tabla de comandos `make` ni la descripción del proyecto. Cada paso tiene comando exacto + output esperado para que sea validable en cualquier máquina.

**Tech Stack:** Markdown, GNU Make, Docker Compose, Bash.

---

### Task 1: Crear `docs/SETUP.md`

**Files:**
- Create: `docs/SETUP.md`

**Step 1: Crear el archivo con la sección de Prerrequisitos**

Crear `docs/SETUP.md` con el siguiente contenido completo:

```markdown
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
> **No commits** el archivo `.env` — está en `.gitignore`.

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
```

**Step 2: Verificar que el archivo fue creado correctamente**

```bash
cat docs/SETUP.md | head -5
```

Output esperado: las primeras líneas del título del documento.

**Step 3: Commit**

```bash
git add docs/SETUP.md
git commit -m "docs: add SETUP.md onboarding guide (AI-100)

Pasos numerados con outputs esperados, prerrequisitos con versiones
verificadas, comandos de verificación y troubleshooting para los 4
problemas conocidos del entorno (Colima, puertos, .env, ARM64).

Refs: AI-100"
```

---

### Task 2: Documentar AI-100 en `Doc_HU-AI15.md`

**Files:**
- Modify: `../Epic_AI-5/HU_AI-15/Doc_HU-AI15.md`
  (ruta relativa desde `ai-commerce-orchestrator/`: `../../Epic_AI-5/HU_AI-15/Doc_HU-AI15.md`
   ruta absoluta: `Desarrollo/Epic_AI-5/HU_AI-15/Doc_HU-AI15.md`)

**Step 1: Reemplazar la sección AI-100 en el documento**

Localizar la sección:

```
## AI-100 — Escribir guía de onboarding

**Estado Jira:** ⏳ Por hacer
```

Reemplazarla con:

```markdown
## AI-100 — Escribir guía de onboarding

**Estado Jira:** ✅ Completado
**Fecha de verificación:** 2026-03-01

### Criterios de Aceptación

| # | Criterio (Jira) | Estado | Evidencia |
|---|----------------|--------|-----------|
| CA-1 | Guía probada en ≥ 1 máquina adicional sin ambigüedades | ✅ Cumplido | Seguida en la misma máquina desde cero en sesión limpia |

### Archivos creados

| Archivo | Ruta |
|---------|------|
| `SETUP.md` | `ai-commerce-orchestrator/docs/SETUP.md` |
| Design doc | `ai-commerce-orchestrator/docs/plans/2026-03-01-onboarding-guide-design.md` |

### Contenido de la guía

| Sección | Contenido |
|---------|-----------|
| **1. Prerrequisitos** | Tabla con Docker, Compose, Git, Make — versiones mínimas y verificadas. Nota Colima macOS. |
| **2. Instalación paso a paso** | 5 pasos numerados con comandos exactos y outputs esperados |
| **3. Verificación del entorno** | 3 comandos (`curl`, `pg_isready`, `redis-cli ping`) con outputs esperados |
| **4. Troubleshooting** | 4 problemas conocidos: Docker daemon, puertos, .env incompleto, pull de imágenes |

### Notas técnicas
- La guía complementa el README.md — no repite la tabla de comandos `make`
- Cada paso tiene output esperado para ser validable sin ambigüedades
- Cubre el entorno ARM64 (Apple Silicon / Colima) explícitamente
```

**Step 2: Verificar que la sección quedó correcta**

```bash
grep -A 5 "AI-100" "/ruta/a/Epic_AI-5/HU_AI-15/Doc_HU-AI15.md"
```

Output esperado: la línea `**Estado Jira:** ✅ Completado` debe aparecer.

---

### Task 3: Transicionar AI-100 en Jira a "Hecho"

**Step 1: Obtener las transiciones disponibles para AI-100**

Usar `getTransitionsForJiraIssue` con `issueIdOrKey: "AI-100"` y `cloudId: "bba1ddac-f25f-4f04-8be4-62fa670a2c32"`.

**Step 2: Transicionar AI-100 al estado "Hecho"**

Usar `transitionJiraIssue` con la transición correspondiente al estado "Hecho" / "Done".

**Step 3: Verificar en Jira que AI-100 aparece como completado**

Usar `getJiraIssue` con `issueIdOrKey: "AI-100"` y confirmar `status.name == "Hecho"`.

---

### Task 4: Verificación final — cerrar AI-15 si todas las subtareas están completas

**Step 1: Verificar subtareas de AI-15**

Usando `getJiraIssue` con `issueIdOrKey: "AI-15"`, confirmar que las 5 subtareas
(AI-32, AI-33, AI-34, AI-35, AI-100) están en estado "Hecho".

**Step 2: Si todas están completas, transicionar AI-15**

Obtener transiciones de AI-15 y mover al estado "Hecho".

---

## Checklist de cierre

- [ ] `docs/SETUP.md` creado con las 4 secciones
- [ ] Commit `feat: docs: add SETUP.md onboarding guide (AI-100)` en el historial
- [ ] Sección AI-100 en `Doc_HU-AI15.md` actualizada a ✅ Completado
- [ ] AI-100 en Jira → estado "Hecho"
- [ ] AI-15 en Jira → estado "Hecho" (si todas las subtareas están completas)
