# Design: Guía de Onboarding (AI-100)

> **Fecha:** 2026-03-01 | **Historia Jira:** AI-100 | **Sprint:** SCRUM Sprint 0
> **Entregable:** `docs/SETUP.md`

---

## Contexto

AI-100 es la última subtarea de AI-15 ("Configurar entorno local con Docker"). Las otras 4 subtareas
(AI-32, AI-33, AI-34, AI-35) están completadas. La descripción de AI-100 en Jira dice:

> "Redactar docs/SETUP.md con pasos numerados, prerrequisitos, troubleshooting.
> Validar ejecutando en una segunda máquina."

**Criterio de aceptación:** Guía probada en ≥ 1 máquina adicional sin ambigüedades.

El README.md ya tiene un quick start de 4 pasos y la tabla de comandos `make`.
`docs/SETUP.md` **complementa** el README — no lo reemplaza.

---

## Decisión de diseño

**Enfoque A — Doc complementario** (elegido sobre B y C).

- `docs/SETUP.md` cubre lo que el README no tiene: prerrequisitos detallados,
  pasos con outputs esperados, verificación y troubleshooting.
- No repite la tabla de comandos `make` ni la descripción del proyecto.
- Alcance mínimo para cerrar AI-100 limpiamente (YAGNI).

---

## Estructura del documento

```
docs/SETUP.md
├── ## 1. Prerrequisitos
├── ## 2. Instalación paso a paso
├── ## 3. Verificación del entorno
└── ## 4. Troubleshooting
```

---

## Contenido por sección

### §1 Prerrequisitos
Tabla: herramienta | versión mínima | versión verificada | link de instalación.
Cubre: Docker Engine (≥24.x, verificado 28.5.2), Docker Compose (≥2.20, verificado 5.1.0),
Git (≥2.x), GNU Make. Nota específica macOS: Colima debe estar corriendo.

### §2 Instalación paso a paso — 5 pasos
1. Clonar el repositorio
2. Copiar `.env.example → .env` y editar `DB_PASSWORD` y `LLM_API_KEY`
3. `make setup` → output esperado: `✅ Todas las variables de entorno están configuradas.`
4. `make up` → los 3 servicios (backend, db, redis) levantando con health checks
5. `docker compose -f infra/docker-compose.yml ps` → todos los servicios en estado `healthy`

Cada paso incluye el comando exacto y el output esperado para que sea validable sin ambigüedades.

### §3 Verificación — 3 comandos de comprobación
- `curl -s http://localhost:8000` → backend responde
- `docker compose -f infra/docker-compose.yml exec db pg_isready` → PostgreSQL acepta conexiones
- `docker compose -f infra/docker-compose.yml exec redis redis-cli ping` → `PONG`

### §4 Troubleshooting — 4 problemas conocidos
| Problema | Causa | Solución |
|---|---|---|
| Cannot connect to Docker daemon | Colima no está corriendo | `colima start` |
| Port already in use (5432/6379/8000) | Otro proceso ocupa el puerto | Cambiar `*_PORT` en `.env` |
| Variables faltantes en `.env` | `.env` incompleto | Revisar output de `make setup`; copiar desde `.env.example` |
| Imagen no descarga | Red o registro inaccesible | Todas las imágenes son `alpine`/`slim`, compatibles ARM64 |

---

## Criterio de cierre

- [ ] `docs/SETUP.md` creado y committeado
- [ ] Guía seguida en ≥ 1 máquina adicional sin necesitar aclaraciones
- [ ] Sección AI-100 completada en `Epic_AI-5/HU_AI-15/Doc_HU-AI15.md`
