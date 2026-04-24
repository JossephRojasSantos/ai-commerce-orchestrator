# Observability — AI Commerce Orchestrator

## Logging

structlog with JSON output in production (`APP_ENV=production`) and console in development.

Every request emits a log with:

| Field | Type | Example |
|-------|------|---------|
| `event` | string | `"request"` |
| `method` | string | `"GET"` |
| `path` | string | `"/products"` |
| `status` | int | `200` |
| `duration_ms` | float | `12.4` |
| `trace_id` | string | `"a1b2c3..."` |

Errors 5xx also include `exc_info` with full stacktrace (via structlog `format_exc_info` processor).

Set `LOG_LEVEL=DEBUG` for verbose output.

## Metrics

Prometheus metrics exposed at `GET /metrics`. Set `METRICS_ENABLED=false` to disable.

| Metric | Type | Labels |
|--------|------|--------|
| `http_requests_total` | Counter | method, path, status |
| `http_request_duration_seconds` | Histogram | method, path |
| `http_errors_total` | Counter | method, path, status |

Histogram buckets: 5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s.

## Grafana Dashboard

Access: `http://localhost:3000` (default credentials: admin / admin or `GRAFANA_PASSWORD`).

Add Prometheus datasource: `http://prometheus:9090`.

Key panels to create:
- **RPS**: `rate(http_requests_total[1m])`
- **Latency p50**: `histogram_quantile(0.5, rate(http_request_duration_seconds_bucket[5m]))`
- **Latency p95**: `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))`
- **Error rate**: `rate(http_errors_total[1m]) / rate(http_requests_total[1m])`

## Alert Thresholds

| Alert | Condition | Severity |
|-------|-----------|----------|
| High error rate | error_rate > 5% over 5min | critical |
| High p95 latency | p95 > 1s over 5min | warning |
| High p95 latency | p95 > 3s over 5min | critical |
| Service down | `up == 0` | critical |

## Smoke Test

```bash
# Against local stack
bash scripts/smoke-test.sh

# Against production
BACKEND_URL=https://api.yourdomain.com bash scripts/smoke-test.sh
```
