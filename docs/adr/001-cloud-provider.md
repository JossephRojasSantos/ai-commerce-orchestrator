# ADR-001: Selección de Proveedor de Infraestructura Cloud

- **Estado:** Aceptado
- **Fecha:** 2026-05-02
- **Historia:** AI-24
- **Autor:** Josseph Rojas Santos

---

## Contexto

El sistema AI Commerce Orchestrator requiere un proveedor cloud para despliegue productivo con los siguientes requisitos:

- Costo mensual ≤ USD 15 total
- Soporte Docker/container nativo
- Baja latencia hacia LATAM (Colombia)
- TLS automático o soportado
- Capacidad suficiente para FastAPI + Redis + LangGraph

---

## Opciones evaluadas

### Matriz de decisión

| Criterio | Peso | Oracle Cloud Free | Hetzner CX22 | Railway Hobby | Fly.io |
|----------|------|:-----------------:|:------------:|:-------------:|:------:|
| Costo mensual ≤ $15 | 30% | ✅ $0 (Free Tier) | ✅ ~$4.5 | ⚠️ $5 + uso | ⚠️ $0 + uso |
| Soporte Docker | 20% | ✅ Completo | ✅ Completo | ✅ Nativo | ✅ Nativo |
| Latencia LATAM | 20% | ⚠️ us-east (68ms) | ❌ EU (160ms) | ✅ us-east (70ms) | ✅ us-east (72ms) |
| RAM / CPU | 15% | ✅ 24GB / 4 OCPU ARM64 | ✅ 4GB / 2 vCPU | ⚠️ 512MB límite | ⚠️ 256MB compartido |
| PostgreSQL managed | 10% | ⚠️ Self-hosted | ✅ Add-on | ✅ Plugin | ✅ Plugin |
| Madurez / DX | 5% | ⚠️ OCI CLI complejo | ✅ Simple | ✅ CLI excelente | ✅ CLI excelente |
| **Score ponderado** | | **0.87** | **0.72** | **0.74** | **0.70** |

### Detalle por candidato

**Oracle Cloud Free Tier (elegido)**
- 4x ARM64 OCPU, 24 GB RAM, 200 GB storage — permanentemente gratis
- Ubuntu 22.04, Docker Compose, cualquier imagen OCI/Docker Hub
- IP pública fija, puertos abiertos vía Security List
- TLS via Nginx reverse proxy + Let's Encrypt (Certbot)
- Desventaja: panel OCI más complejo; ARM64 requiere imágenes multi-arch

**Hetzner CX22**
- €4.51/mes (~$4.9), 4 vCPU x86, 4 GB RAM, datacenter EU
- Excelente para Europa; latencia a Colombia ~160ms — fuera de objetivo
- Sin Free Tier permanente

**Railway Hobby**
- $5/mes base + consumo de RAM/CPU/egress
- Latencia LATAM aceptable, DX excelente, pero RAM limitada (512MB)
- Puede superar $15/mes con tráfico moderado

**Fly.io**
- $0 base + consumo; muy buena DX y CLI
- Machines comparten recursos; cold start en tier gratuito
- Egress puede elevar costo fácilmente

---

## Decisión

**Oracle Cloud Free Tier (región us-ashburn-1)**

Razones principales:
1. Costo $0 permanente — cumple holgadamente el presupuesto
2. 24 GB RAM / 4 OCPU permite correr FastAPI + Redis + LangGraph simultáneamente sin restricciones
3. IP pública fija facilita configuración de DNS y TLS
4. Latencia desde Colombia ~68ms — aceptable para el caso de uso

---

## Prueba de concepto (PoC)

| Evidencia | Valor |
|-----------|-------|
| URL de producción | `https://api.tiendamagica.shop` |
| Health check | `GET /health/` → `{"status":"ok","version":"0.1.0"}` |
| Servicios corriendo | FastAPI + Redis + LangGraph en Docker Compose |
| TLS | Let's Encrypt via Nginx (A en SSL Labs) |
| Costo real a la fecha | $0.00 USD/mes |
| Uptime desde deploy | 2026-04-28 (CI/CD automático via GitHub Actions) |

---

## Consecuencias

- **Positivo:** Costo cero libera presupuesto para otros recursos (LLM API, dominio)
- **Positivo:** Recursos generosos permiten experimentar con modelos locales en el futuro
- **Negativo:** ARM64 requiere buildx multi-arch en el pipeline de CD (ya implementado)
- **Negativo:** OCI no ofrece managed PostgreSQL en Free Tier — se usa PostgreSQL en Docker (aceptable para proyecto de grado)
- **Negativo:** Sin SLA en Free Tier — aceptable para contexto académico
