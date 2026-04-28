# SmartSRE Copilot

> AI-powered SRE copilot for knowledge-grounded chat, operational document search, and AIOps diagnosis.
>
> 面向 SRE / On-call / AIOps 场景的智能运维助手，支持知识库问答、文档向量化、流式对话和可选 MCP 工具接入。

[![Python](https://img.shields.io/badge/Python-3.11%20--%203.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic-orange.svg)](https://www.langchain.com/langgraph)
[![Next.js](https://img.shields.io/badge/Next.js-Frontend-black.svg)](https://nextjs.org/)
[![CI](https://github.com/Mobicos/smartsre-copilot-py/actions/workflows/ci.yml/badge.svg)](https://github.com/Mobicos/smartsre-copilot-py/actions/workflows/ci.yml)

## Overview / 项目概览

SmartSRE Copilot is a production-oriented prototype for building an internal SRE assistant. The backend is a FastAPI service with LangChain/LangGraph agents, DashScope/Qwen models, PostgreSQL persistence, Redis-backed background tasks, and Milvus vector search. The frontend is a modern Next.js app that talks to the backend through server-side route handlers.

SmartSRE Copilot 是一个面向企业内部运维场景的智能助手原型。后端基于 FastAPI、LangChain/LangGraph、DashScope/Qwen、PostgreSQL、Redis 和 Milvus；前端基于 Next.js，通过服务端 BFF 路由访问后端，避免把后端密钥暴露到浏览器。

Core capabilities:

- Knowledge-grounded chat over uploaded `.txt` and `.md` documents.
- Streaming chat responses and persisted conversation history.
- Background indexing pipeline with retryable tasks.
- Plan-Execute-Replan AIOps diagnosis workflow.
- Optional MCP tool integration for external logs, metrics, and alert systems.

核心能力：

- 基于上传文档的知识库问答。
- 流式对话和会话历史持久化。
- 后台异步索引任务和失败重试。
- Planner / Executor / Replanner 模式的 AIOps 诊断流程。
- 可选 MCP 工具接入外部日志、指标和告警系统。

## Architecture / 架构

```text
Browser
  |
  v
Next.js frontend (frontend/)
  |
  | server-side route handlers / BFF
  v
FastAPI backend (app/)
  |
  +-- Chat / RAG ----------------> Qwen Chat model
  |                                + retrieve_knowledge tool
  |                                + optional MCP tools
  |
  +-- Upload / indexing ---------> Redis queue
  |                                + worker
  |                                + DashScope embeddings
  |                                + Milvus collection: biz
  |
  +-- AIOps diagnosis -----------> Planner -> Executor -> Replanner
  |                                + local tools
  |                                + optional MCP tools
  |
  +-- Persistence ---------------> PostgreSQL
```

```text
浏览器
  |
  v
Next.js 前端 (frontend/)
  |
  | 服务端路由代理 / BFF
  v
FastAPI 后端 (app/)
  |
  +-- 对话 / RAG ----------------> Qwen 对话模型
  |                                + 知识库检索工具
  |                                + 可选 MCP 工具
  |
  +-- 上传 / 索引 ---------------> Redis 队列
  |                                + 独立 worker
  |                                + DashScope Embedding
  |                                + Milvus collection: biz
  |
  +-- AIOps 诊断 ----------------> Planner -> Executor -> Replanner
  |                                + 本地工具
  |                                + 可选 MCP 工具
  |
  +-- 持久化 --------------------> PostgreSQL
```

## Tech Stack / 技术栈

Backend:

- FastAPI, Pydantic Settings, Server-Sent Events
- LangChain, LangGraph, Qwen via DashScope
- PostgreSQL, Alembic, Redis, Milvus
- MCP client support for external tool servers

Frontend:

- Next.js, React, TypeScript
- Server-side API route handlers as a BFF layer
- pnpm lockfile committed for reproducible frontend installs

后端：

- FastAPI、Pydantic Settings、SSE
- LangChain、LangGraph、DashScope/Qwen
- PostgreSQL、Alembic、Redis、Milvus
- 支持 MCP 客户端接入外部工具服务

前端：

- Next.js、React、TypeScript
- 使用服务端 API Route 作为 BFF 层
- 提交 `pnpm-lock.yaml` 保证前端依赖可复现

## Repository Layout / 目录结构

```text
app/              FastAPI backend, agents, services, persistence
alembic/          PostgreSQL schema migrations
frontend/         Next.js frontend application
mcp_servers/      Local/mock MCP server examples
tests/            Backend tests
aiops-docs/       Sample operational documents
uploads/          Local uploaded files, ignored by Git
data/             Local SQLite/data files, ignored by Git
volumes/          Docker service data, ignored by Git
```

```text
app/              FastAPI 后端、Agent、服务层、持久化层
alembic/          PostgreSQL 数据库迁移
frontend/         Next.js 前端应用
mcp_servers/      本地/mock MCP 服务示例
tests/            后端测试
aiops-docs/       示例运维文档
uploads/          本地上传文件，Git 忽略
data/             本地数据文件，Git 忽略
volumes/          Docker 服务数据，Git 忽略
```

## Data Ownership / 数据边界

Local application data stays local unless you explicitly connect external tools.

- Uploaded files are stored under `uploads/`.
- Chat history, task status, audit logs, and AIOps run events are stored in PostgreSQL.
- Document vectors are stored in Milvus.
- DashScope receives prompts and embedding inputs required for model calls.
- MCP tools are optional. A Tencent Cloud CLS MCP server queries Tencent CLS data, not local Postgres or Milvus data.

本地应用数据默认保存在本地，除非你显式接入外部工具。

- 上传文件保存在 `uploads/`。
- 会话历史、任务状态、审计日志、AIOps 事件保存在 PostgreSQL。
- 文档向量保存在 Milvus。
- DashScope 会收到模型调用所需的 prompt 和 embedding 输入。
- MCP 是可选工具入口。腾讯云 CLS MCP 查询的是腾讯云 CLS 数据，不是本地 Postgres 或 Milvus 数据。

## Prerequisites / 前置要求

- Python `3.11` to `3.13`
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

## Quick Start / 快速开始

### 1. Backend environment / 后端环境

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

至少需要修改 `.env` 中的 `DASHSCOPE_API_KEY` 和本地 API key 配置。

### 2. Start infrastructure / 启动基础设施

For the full Docker stack:

```bash
docker compose up -d --build
```

This starts PostgreSQL, Redis, Milvus, Attu, MinIO, migrations, backend app, and worker.

如果你采用“本地 Python 后端 + Docker 基础设施”的开发模式，可以只保留数据库、Redis、Milvus 等基础设施运行，然后用 `uv` 启动后端。项目根目录中的 `docker-compose.local.yml` 如果存在，通常是本地实验配置，不建议直接提交。

### 3. Run database migrations / 执行数据库迁移

```bash
uv run alembic upgrade head
```

### 4. Run backend locally / 本地启动后端

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 9900
```

If `TASK_DISPATCHER_MODE=detached`, start the indexing worker in another terminal:

```bash
uv run python -m app.worker
```

如果使用 `detached` 模式，上传文档后必须启动 worker，否则索引任务只会入队不会消费。

### 5. Run frontend locally / 本地启动前端

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

不要把后端密钥写到 `NEXT_PUBLIC_*` 环境变量里。

### 6. Open the services / 打开服务

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API: [http://localhost:9900](http://localhost:9900)
- Backend docs: [http://localhost:9900/docs](http://localhost:9900/docs)
- Health check: [http://localhost:9900/health](http://localhost:9900/health)
- Attu, if using default compose: [http://localhost:8000](http://localhost:8000)

## Configuration / 配置说明

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
- `DATABASE_BACKEND`: `postgres` or `sqlite`
- `POSTGRES_DSN`: PostgreSQL DSN
- `REDIS_URL`: Redis connection string
- `TASK_QUEUE_BACKEND`: `redis` or `database`
- `TASK_DISPATCHER_MODE`: `embedded` or `detached`
- `MILVUS_HOST`, `MILVUS_PORT`: vector database connection
- `RAG_TOP_K`: retrieval result count
- `CHUNK_MAX_SIZE`, `CHUNK_OVERLAP`: document splitting
- `MCP_CLS_TRANSPORT`, `MCP_CLS_URL`: optional CLS MCP server
- `MCP_MONITOR_TRANSPORT`, `MCP_MONITOR_URL`: optional monitor MCP server
- `MCP_TOOLS_LOAD_TIMEOUT_SECONDS`: tool discovery timeout

Production guidance:

- Set `ENVIRONMENT=prod` or `ENVIRONMENT=production`.
- Configure explicit `CORS_ALLOWED_ORIGINS`; do not use `*`.
- Configure `APP_API_KEY` or `API_KEYS_JSON`.
- Keep `.env` out of Git.
- Prefer managed PostgreSQL, Redis, and Milvus/Zilliz for production.

生产建议：

- 生产环境设置 `ENVIRONMENT=prod` 或 `production`。
- CORS 必须配置明确域名，不要使用 `*`。
- 必须配置 API key。
- 不要提交 `.env`。
- 生产环境优先使用托管 PostgreSQL、Redis 和 Milvus/Zilliz。

## MCP Integration / MCP 接入

MCP is optional. The application works without MCP for knowledge-base chat and document RAG. AIOps workflows can use MCP tools when external log, metrics, and alert systems are configured.

MCP 是可选能力。知识库问答和文档 RAG 不依赖 MCP；AIOps 诊断在配置外部日志、指标、告警工具后可以调用 MCP。

Recommended practices:

- Use local or internal self-hosted MCP servers for development and production.
- Treat cloud-hosted MCP SSE endpoints as quick evaluation links unless you have clear operational guarantees.
- Keep cloud credentials in server-side environment variables only.
- If MCP tools fail to load, the backend should report unavailable tools instead of inventing tool names.

最佳实践：

- 本地开发和生产环境优先使用自建 MCP Server。
- 云厂商托管 SSE 更适合快速体验，不建议作为正式链路的唯一依赖。
- 云账号密钥只放服务端环境变量。
- MCP 工具加载失败时应明确提示不可用，不能让 Agent 编造工具。

Example local MCP settings:

```env
MCP_CLS_TRANSPORT=streamable-http
MCP_CLS_URL=http://localhost:8003/mcp
MCP_MONITOR_TRANSPORT=streamable-http
MCP_MONITOR_URL=http://localhost:8004/mcp
MCP_TOOLS_LOAD_TIMEOUT_SECONDS=30
```

## API Summary / API 概览

Backend routes:

- `GET /health`: service health
- `POST /api/chat`: non-streaming chat
- `POST /api/chat_stream`: streaming chat via SSE
- `GET /api/chat/sessions`: persisted chat sessions
- `GET /api/chat/session/{session_id}`: session history
- `POST /api/upload`: upload and enqueue document indexing
- `GET /api/index_tasks/{task_id}`: indexing task status
- `POST /api/aiops`: streaming AIOps diagnosis via SSE
- `GET /api/aiops/runs/{run_id}`: AIOps run summary
- `GET /api/aiops/runs/{run_id}/events`: AIOps run events

前端通过 `frontend/app/api/*` 的服务端路由代理后端，浏览器组件不直接调用 FastAPI。

## Development Workflow / 开发流程

Recommended backend commands:

```bash
uv run python -m compileall app mcp_servers tests
uv run python -m ruff check app mcp_servers tests
uv run python -m ruff format --check app mcp_servers tests
uv run python -m mypy app --ignore-missing-imports
uv run python -m bandit -r app -ll
uv run python -m pytest tests -q
```

Recommended frontend commands:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm build
```

Common Make targets:

```bash
make up
make down
make status
make db-upgrade
make test
make lint
make type-check
make security
```

开发建议：

- 后端依赖以 `pyproject.toml` 为准，`uv.lock` 必须提交。
- 前端依赖以 `frontend/package.json` 和 `frontend/pnpm-lock.yaml` 为准。
- 不要提交 `.env`、`.venv/`、`uploads/`、`data/`、`volumes/`、`frontend/node_modules/`、`frontend/.next/`。
- 后端 API 模型变化时，同步更新 `frontend/lib/api-contracts.ts` 或 BFF 路由适配层。

## Operational Notes / 运行说明

Document indexing:

```text
POST /api/upload
  -> save file under uploads/
  -> create indexing task
  -> enqueue task
  -> worker reads file
  -> split text
  -> embed chunks
  -> write vectors to Milvus
```

Chat:

```text
Frontend chat
  -> Next.js BFF
  -> FastAPI /api/chat_stream
  -> RagAgentService
  -> retrieve_knowledge
  -> Milvus
  -> Qwen streaming response
```

AIOps:

```text
Frontend diagnose
  -> Next.js BFF
  -> FastAPI /api/aiops
  -> Planner
  -> Executor
  -> Replanner
  -> persisted run events
```

## Troubleshooting / 故障排查

Backend cannot start:

- Check `PORT` availability.
- Verify `.env` values.
- Ensure PostgreSQL and Milvus are reachable.
- Run `uv run alembic upgrade head`.

后端无法启动：

- 检查端口是否被占用。
- 检查 `.env`。
- 确认 PostgreSQL 和 Milvus 可达。
- 执行数据库迁移。

Upload succeeds but indexing never completes:

- Check `TASK_DISPATCHER_MODE`.
- If `detached`, start `uv run python -m app.worker`.
- Check Redis connectivity and task status endpoint.

上传成功但索引不完成：

- 检查 `TASK_DISPATCHER_MODE`。
- 如果是 `detached`，启动 worker。
- 检查 Redis 和索引任务状态接口。

MCP tools unavailable:

- Confirm MCP URL and transport are correct.
- Increase `MCP_TOOLS_LOAD_TIMEOUT_SECONDS` if tool discovery is slow.
- Test the MCP server independently before blaming the Agent.
- Remember that Tencent CLS MCP queries Tencent CLS data, not local app data.

MCP 工具不可用：

- 确认 MCP URL 和 transport。
- 工具发现慢时提高 `MCP_TOOLS_LOAD_TIMEOUT_SECONDS`。
- 先独立测试 MCP Server，再排查 Agent。
- 腾讯 CLS MCP 查询的是腾讯 CLS 数据，不是本地应用数据。

Frontend cannot reach backend:

- Check `frontend/.env.local`.
- Ensure `SMARTSRE_BACKEND_URL` points to the FastAPI service.
- If backend auth is enabled, set `SMARTSRE_API_KEY` server-side only.

前端无法访问后端：

- 检查 `frontend/.env.local`。
- 确认 `SMARTSRE_BACKEND_URL` 指向 FastAPI。
- 如果后端启用了 API key，配置 `SMARTSRE_API_KEY`。

## Security Best Practices / 安全最佳实践

- Keep all secrets in environment variables or a secret manager.
- Do not expose backend API keys to browser code.
- Use explicit CORS origins in production.
- Use least-privilege cloud credentials for MCP servers.
- Store audit logs and AIOps run events in durable storage.
- Review uploaded document access rules before exposing the app to multiple teams.

安全建议：

- 所有密钥放环境变量或密钥管理系统。
- 不要把后端 API key 暴露给浏览器。
- 生产环境使用明确 CORS 白名单。
- MCP 云账号使用最小权限。
- 审计日志和 AIOps 运行事件使用持久化存储。
- 多团队使用前先设计上传文档的权限边界。

## Contributing / 贡献

Commit messages follow simplified Conventional Commits:

```text
docs: update project README
fix: handle indexing retry failure
feat: add diagnosis event timeline
```

See `AGENTS.md` for repository-specific coding, dependency, CI, and frontend policies.

提交信息遵循简化 Conventional Commits。更多工程规范见 `AGENTS.md`。

## License / 许可证

MIT
