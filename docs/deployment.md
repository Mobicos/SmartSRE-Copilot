# Deployment Guide

SmartSRE Copilot can run as a local development stack or as a controlled
internal evaluation deployment. The current development stack uses
PostgreSQL, Redis, Milvus, FastAPI, and Next.js.

## Prerequisites

- Python `3.11+`
- `uv` for Python dependency management
- Docker Desktop, OrbStack, Colima, or another Docker runtime
- Node.js and `pnpm` for frontend development
- DashScope API key

```bash
python --version
uv --version
docker --version
node --version
pnpm --version
```

## Quick Start

### 1. Backend Environment

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
cp .env.example .env
```

Edit `.env` and set at least:

```env
DASHSCOPE_API_KEY=your_dashscope_api_key
APP_API_KEY=replace_with_a_secure_key
ENVIRONMENT=dev
```

### 2. Start Infrastructure

**Option A: Full Docker Stack (recommended for testing)**

```bash
docker compose up -d --build
```

This starts all services: PostgreSQL (5432), Redis (6379), Milvus (19530), Attu
(8000), MinIO (9000/9001), migrations, backend app (9900), and worker.

**Option B: Local Development (recommended for development)**

Use `docker-compose.yml` as the shared template, then copy it to an ignored
`docker-compose.local.yml` for personal machine overrides.

1. Copy the shared compose template:

   ```bash
   cp docker-compose.yml docker-compose.local.yml
   ```

1. Edit `docker-compose.local.yml` for your machine.

   Common local changes:

   - Change exposed ports if PostgreSQL, Redis, Milvus, Attu, or MinIO conflict
     with services already running on your machine.
   - Remove or comment out `app`, `worker`, and `migrate` if you prefer running
     Python locally with `uv`.
   - Keep service names such as `postgres`, `redis`, and `standalone` unchanged
     if other compose services still depend on them.

1. Start the local compose stack:

   ```bash
   docker compose -f docker-compose.local.yml up -d
   ```

   If you only need infrastructure for local Python development, start those
   services directly:

   ```bash
   docker compose -f docker-compose.local.yml up -d postgres redis standalone attu minio
   ```

1. Update your `.env` to match your local exposed ports.

   Example when local ports are shifted to avoid conflicts:

   ```env
   POSTGRES_DSN=postgresql://smartsre:smartsre@localhost:5433/smartsre
   REDIS_URL=redis://localhost:6380/0
   MILVUS_HOST=localhost
   MILVUS_PORT=19531
   ```

1. Run backend and frontend locally with `uv` and `pnpm` (see steps 3-5 below).

**Note**: `docker-compose.local.yml` is ignored by Git and should be treated as
local-only configuration. Do not commit personal port mappings, local paths, or
machine-specific service deletions.

### 3. Run Database Migrations

```bash
uv run alembic upgrade head
```

### 4. Run Backend Locally

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 9900
```

If `TASK_DISPATCHER_MODE=detached`, start the indexing worker in another
terminal:

```bash
uv run python -m app.worker
```

### 5. Run Frontend Locally

```bash
cd frontend
pnpm install --frozen-lockfile
cp .env.example .env.local
pnpm dev
```

Default frontend backend target:

```text
SMARTSRE_BACKEND_URL=http://localhost:9900
```

If backend API key auth is enabled, set this only in `frontend/.env.local`:

```env
SMARTSRE_API_KEY=your_backend_api_key
```

Do not expose backend secrets through `NEXT_PUBLIC_*`.

### 6. Open the Services

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API: [http://localhost:9900](http://localhost:9900)
- Backend docs: [http://localhost:9900/docs](http://localhost:9900/docs)
- Health check: [http://localhost:9900/health](http://localhost:9900/health)
- Prometheus metrics: [http://localhost:9900/metrics](http://localhost:9900/metrics)
- Attu, if using default compose: [http://localhost:8000](http://localhost:8000)

## Compose Profiles And Smoke

The default compose stack starts the app path: PostgreSQL, Redis, MinIO,
migrations, FastAPI backend, worker, and Next.js frontend. Optional profiles add
deployment and observability services:

- `gateway`: adds Caddy for the production-style reverse proxy path.
- `observability`: adds Prometheus, Loki, and OpenTelemetry collector services.
- `vector-milvus`: starts the Milvus/Attu vector-store stack when pgvector is not
  enough for local validation.

Validate the full production-style compose graph:

```bash
docker compose -f docker-compose.yml --profile gateway --profile observability config --quiet
```

Run the local non-destructive smoke check:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\compose_smoke.ps1
```

The smoke script uses `ENVIRONMENT=dev` and
`AGENT_DECISION_PROVIDER=deterministic` by default so it does not require a real
Qwen key. It verifies service health, migration completion, backend `/health`,
backend `/metrics`, the frontend, and the Caddy gateway.

If Docker fails with a proxy error such as `127.0.0.1:7890 refused`, start the
local proxy configured in Docker Desktop, or clear Docker Desktop proxy settings
and retry a direct image pull such as `docker pull pgvector/pgvector:pg16`.
After image pulls work, rerun the smoke script.

## Configuration

Backend settings are defined in `app/config.py` and loaded from `.env`.

Key backend variables:

- `ENVIRONMENT`: `dev`, `prod`, or `production`
- `DEBUG`: enable development behavior
- `HOST`, `PORT`: backend bind address
- `CORS_ALLOWED_ORIGINS`: explicit allowlist for browser origins
- `APP_API_KEY` or `API_KEYS_JSON`: API key based access control
- `DASHSCOPE_API_KEY`: DashScope model access
- `DASHSCOPE_MODEL`, `RAG_MODEL`: chat models
- `DASHSCOPE_EMBEDDING_MODEL`: embedding model
- `POSTGRES_DSN`: PostgreSQL DSN (with pgvector extension)
- `REDIS_URL`: Redis connection string
- `TASK_QUEUE_BACKEND`: `redis` or `database`
- `TASK_DISPATCHER_MODE`: `embedded` or `detached`
- `VECTOR_STORE_BACKEND`: `pgvector` (default) or `milvus`
- `PGVECTOR_COLLECTION_NAME`: pgvector collection name (default `biz`)
- `MILVUS_HOST`, `MILVUS_PORT`: Milvus connection (only when using Milvus backend)
- `RAG_TOP_K`: retrieval result count
- `CHUNK_MAX_SIZE`, `CHUNK_OVERLAP`: document splitting
- `MCP_CLS_TRANSPORT`, `MCP_CLS_URL`: optional CLS MCP server
- `MCP_MONITOR_TRANSPORT`, `MCP_MONITOR_URL`: optional monitor MCP server
- `MCP_TOOLS_LOAD_TIMEOUT_SECONDS`: tool discovery timeout

Production guidance:

- Set `ENVIRONMENT=prod` or `ENVIRONMENT=production`.
- Configure explicit `CORS_ALLOWED_ORIGINS`; do not use `*`.
- Configure `APP_API_KEY` or `API_KEYS_JSON`.
- Set `AGENT_DECISION_PROVIDER=qwen` and provide a real `DASHSCOPE_API_KEY`.
- Replace all PostgreSQL, MinIO, Redis, and API-key placeholders with unique
  production secrets.
- Keep Prometheus scraping the backend `/metrics` endpoint and keep
  OpenTelemetry tracing configured separately when tracing is required.
- Keep `.env` out of Git.
- Prefer managed PostgreSQL, Redis, and Milvus/Zilliz for production.
- Define backup and restore procedures for PostgreSQL, object storage, and any
  vector-store data before onboarding real incident data.

## Local Development

Use `docker-compose.yml` as the shared template and copy it to
`docker-compose.local.yml` for personal port or service changes:

```bash
cp docker-compose.yml docker-compose.local.yml
docker compose -f docker-compose.local.yml up -d postgres redis standalone attu minio
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 9900
cd frontend
pnpm dev
```

Do not commit `docker-compose.local.yml`.

## Controlled Evaluation Baseline

For controlled internal evaluation deployments:

- Run FastAPI behind a reverse proxy.
- Run the Next.js frontend as a separate service.
- Use managed or backed-up PostgreSQL.
- Use Redis for queues and short-lived state.
- Use explicit CORS origins.
- Configure API keys server-side.
- Keep MCP credentials least-privilege.
- Run migrations before accepting traffic.

## Update Procedure

1. Read the change notes in the PR or deployment ticket.
1. Back up PostgreSQL.
1. Pull the target image or source revision.
1. Run database migrations.
1. Deploy workers before or with the API when queue schema changes.
1. Deploy the frontend when BFF/API contracts change.
1. Verify `/health`, `/docs`, Agent run creation, and frontend BFF routes.

## Rollback Procedure

1. Stop traffic at the reverse proxy when needed.
1. Roll back frontend and backend together if API contracts changed.
1. Run Alembic downgrade only when the change notes say it is safe.
1. Preserve `agent_events` and audit logs for postmortem review.

## Pre-Production Checklist

- Backend gates pass: compile, Ruff lint and format check, mypy, Bandit,
  OpenAPI check, and the full pytest suite.
- Frontend gates pass: `pnpm install --frozen-lockfile`, lint, typecheck, build,
  and Playwright Agent E2E.
- Compose validation and `scripts\compose_smoke.ps1` pass with gateway and
  observability profiles available.
- Production `.env` is based on `config/.env.prod.example`, with Qwen provider,
  real DashScope key, explicit CORS, API key enforcement, and unique database,
  Redis, and MinIO secrets.
- Prometheus can scrape `/metrics`, and OpenTelemetry tracing remains configured
  independently when enabled.
- Backup and restore are tested for PostgreSQL, object storage, and any external
  vector-store data.
- High-risk or destructive tools require approval, and the approval/resume path
  is tested in the workbench before onboarding real incidents.
