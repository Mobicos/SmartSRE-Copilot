# SmartSRE Copilot

> AI-powered SRE assistant with knowledge-grounded chat, AIOps diagnosis, and
> native agent workbench.

[English](README.md) | [简体中文](docs/README.zh-CN.md)

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic-orange.svg)](https://www.langchain.com/langgraph)
[![Next.js](https://img.shields.io/badge/Next.js-Frontend-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![CI](https://github.com/Mobicos/SmartSRE-Copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/Mobicos/SmartSRE-Copilot/actions/workflows/ci.yml)

## Overview

SmartSRE Copilot is a development-stage Native Agent Workbench for building an
internal SRE assistant. The backend is a FastAPI service with LangChain/
LangGraph agents, DashScope/Qwen models, PostgreSQL persistence, Redis-backed
background tasks, and Milvus vector search. The frontend is a modern Next.js app
that talks to the backend through server-side route handlers.

Core capabilities:

- Knowledge-grounded chat over uploaded `.txt` and `.md` documents.
- Streaming chat responses and persisted conversation history.
- Background indexing pipeline with retryable tasks.
- Plan-Execute-Replan AIOps diagnosis workflow.
- Native Agent workspace, scene, tool policy, trajectory replay, and feedback
  APIs.
- Optional MCP tool integration for external logs, metrics, and alert systems.

## Project Status

**Development stage** — SmartSRE Copilot has not published a stable product
version. The 2.0 production-capability work is implemented except for version
publication, tags, and release artifacts. Verify with quality gates, browser
E2E, compose smoke, and real production secrets before serving production
traffic.

## Architecture

```text
Browser
  |
  v
Next.js frontend (BFF route handlers)
  |
  v
FastAPI backend
  |
  +-- Chat / RAG -----------------> Qwen + MCP tools
  +-- Upload / indexing -----------> Redis + DashScope embeddings
  +-- Native Agent diagnosis ------> AgentRuntime + ToolPolicy
  +-- Decision Runtime -----------> LangGraph StateGraph
  +-- Checkpoint Resume ----------> approval gate + auto-resume
  +-- Persistence ----------------> PostgreSQL + pgvector
```

Full architecture details: [docs/architecture.md](docs/architecture.md)

## Quick Start

### Prerequisites

- Python `3.11+`, `uv`, Docker, Node.js + `pnpm`, DashScope API key

### 1. Backend

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
cp .env.example .env    # set DASHSCOPE_API_KEY and APP_API_KEY
```

### 2. Infrastructure

```bash
# Full stack (recommended)
docker compose up -d --build

# Or local development — start only infrastructure services
cp docker-compose.yml docker-compose.local.yml
docker compose -f docker-compose.local.yml up -d postgres redis standalone attu minio
```

### 3. Migrations & Run

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 9900
```

### 4. Frontend

```bash
cd frontend
pnpm install --frozen-lockfile
cp .env.example .env.local
pnpm dev
```

### Services

- Frontend: http://localhost:3000
- Backend API: http://localhost:9900
- API docs: http://localhost:9900/docs

Full deployment guide: [docs/deployment.md](docs/deployment.md)

## Documentation

| Document | Description |
|----------|-------------|
| [docs/architecture.md](docs/architecture.md) | System architecture, tech stack, data ownership |
| [docs/deployment.md](docs/deployment.md) | Full deployment guide, configuration, compose profiles |
| [docs/api-reference.md](docs/api-reference.md) | Backend API routes, MCP integration |
| [docs/development-workflow.md](docs/development-workflow.md) | Branch workflow, commit format, PR rules |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common issues and solutions |
| [docs/repository-governance.md](docs/repository-governance.md) | Branch protection, labels, maintainer rules |
| [docs/security.md](docs/security.md) | Operational security checklist |
| [docs/openapi.json](docs/openapi.json) | Generated FastAPI OpenAPI contract |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Human contributor workflow |
| [AGENTS.md](AGENTS.md) | AI coding agent execution rules |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting policy |
| [SUPPORT.md](SUPPORT.md) | Support boundaries and issue guidance |
| [MAINTAINERS.md](MAINTAINERS.md) | Maintainer responsibilities |

## Contributing

Read `CONTRIBUTING.md` for the contributor workflow, commit style, branch
policy, PR rules, quality gates, and dependency policy. AI coding agents
should also read `AGENTS.md` before making changes.

Do not create public delivery tags, GitHub delivery artifacts, or package and
container distribution automation while the project is in development stage.

## License

Apache License 2.0. See [LICENSE](LICENSE).
