# CD Pipeline — Continuous Deployment

## Overview

Push to `master` → GitHub Actions builds ARM64 Docker image → pushes to DockerHub → deploys via SSH to Oracle Cloud → smoke test.

| Step | Job | Typical duration |
|---|---|---|
| Build & push image | `build-push` | ~2 min |
| Deploy via SSH | `deploy` | ~30 s |
| Smoke test `/health` | `deploy` | ~25 s |
| **Total** | | **< 4 min** |

Workflow file: `.github/workflows/cd.yml`

---

## Rollback Procedure

### Option A — Re-deploy previous SHA (recommended)

Every successful deploy tags the image with the commit SHA (`dockerhub_user/ai-commerce-backend:<sha>`).

**Step 1** — Find the last known-good SHA:

```bash
# List recent successful CD runs
gh run list --workflow=cd.yml --status success --limit 10
```

**Step 2** — Trigger re-deploy via `workflow_dispatch` with the previous SHA:

```bash
# Set the previous good SHA
PREV_SHA=<previous-sha>

gh workflow run cd.yml \
  --ref master \
  --field image_tag=$PREV_SHA
```

> If `workflow_dispatch` inputs are not wired, use SSH directly (Option B).

**Step 3** — Verify:

```bash
curl -fL https://<server-ip>:8000/health
```

---

### Option B — Manual SSH rollback

```bash
ssh -i ~/.ssh/deploy_key -p <port> <user>@<host>

# On the server:
cd <deploy_path>

export DOCKERHUB_USERNAME=<username>
export IMAGE_TAG=<previous-sha>   # the last known-good SHA

docker compose -f infra/docker-compose.prod.yml pull backend
docker compose -f infra/docker-compose.prod.yml up -d backend

# Verify
curl -f http://localhost:8000/health
docker logs ai-backend --tail 20
```

---

### Option C — Emergency: revert to `latest` stable

If SHA tags are unavailable, `latest` points to the last successful push:

```bash
export IMAGE_TAG=latest
docker compose -f infra/docker-compose.prod.yml up -d backend
```

---

## Smoke Test

Runs automatically after each deploy:

```bash
curl -fL http://localhost:8000/health/ || (docker logs ai-backend --tail 50 && exit 1)
```

Returns `{"status":"ok"}` on success. Workflow fails and stops if `/health` does not respond within 20 s.

---

## Secrets required

| Secret | Description |
|---|---|
| `DOCKERHUB_USERNAME` | DockerHub account |
| `DOCKERHUB_TOKEN` | DockerHub access token (read/write) |
| `DEPLOY_HOST` | Oracle Cloud server IP |
| `DEPLOY_USER` | SSH username |
| `DEPLOY_SSH_KEY` | Private key (ED25519 recommended) |
| `DEPLOY_PORT` | SSH port |
| `DEPLOY_PATH` | Absolute path on server |
| `ENV_PROD` | Full contents of `.env.prod` |

---

## Checking deploy status

```bash
# Last 5 CD runs
gh run list --workflow=cd.yml --limit 5

# Logs of a specific run
gh run view <run-id> --log

# Container logs on server
ssh ... "docker logs ai-backend --tail 100"
```
