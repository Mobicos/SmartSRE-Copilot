# SmartSRE Copilot

> An AI-powered SRE copilot for knowledge-grounded chat, on-call investigation, and AIOps diagnosis.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic-orange.svg)](https://www.langchain.com/langgraph)

SmartSRE Copilot is a FastAPI-based SRE assistant that combines:

- RAG-based knowledge retrieval from operational documents
- LLM chat with local and MCP-based tools
- Plan-Execute-Replan style AIOps diagnosis
- A lightweight web UI for chat, streaming answers, file upload, and diagnosis

## 中文速览

SmartSRE Copilot 是一个面向 SRE / On-call / AIOps 场景的智能助手，当前主要提供三类能力：

- 知识库问答：基于本地运维文档做 RAG 检索增强
- 智能诊断：基于 Planner、Executor、Replanner 做多步排障
- 工具接入：通过 MCP 接入日志和监控查询能力

适合的使用场景：

- 内部运维知识助手
- 故障演练或诊断流程演示
- AIOps Copilot 原型验证

## What It Does

### 1. Knowledge-grounded chat
- Ask operational questions in natural language
- Retrieve relevant content from Markdown or text documents
- Support normal response mode and streaming response mode

### 2. AIOps diagnosis
- Build a diagnosis plan automatically
- Execute investigation steps with available tools
- Re-evaluate progress and produce a final Markdown report

### 3. Tool integration
- Built-in tools for time lookup and knowledge retrieval
- MCP integration for logs and monitoring queries

### 4. Web experience
- Simple static frontend
- Local chat history in the browser
- File upload for knowledge base indexing

## Architecture

```text
Browser UI
   |
   v
FastAPI
   |
   +-- Chat API --------------------> RAG Agent Service
   |                                  |
   |                                  +-- ChatQwen
   |                                  +-- Knowledge Tool
   |                                  +-- Time Tool
   |                                  +-- MCP Tools
   |
   +-- Upload API ------------------> Document Splitter
   |                                  |
   |                                  +-- Embedding Service
   |                                  +-- Milvus Vector Store
   |
   +-- AIOps API -------------------> Planner -> Executor -> Replanner
                                      |
                                      +-- MCP Log Tools
                                      +-- MCP Monitor Tools
```

## Tech Stack

- Backend: FastAPI, SSE, Pydantic Settings
- Agent framework: LangChain, LangGraph
- LLM: DashScope / Qwen
- Vector database: Milvus
- Tool protocol: MCP
- Frontend: static HTML, CSS, JavaScript

## Repository Layout

```text
app/
  api/         HTTP routes
  services/    RAG, indexing, search, AIOps services
  agent/       MCP client and AIOps graph nodes
  core/        Milvus and LLM integration
  tools/       Built-in agent tools
  models/      Request and response models
  utils/       Logging and helpers

static/        Web UI
mcp_servers/   Mock MCP services for logs and monitoring
aiops-docs/    Sample knowledge base documents
```

## Current Scope

This project is best viewed as an internal demo or prototype for SRE workflows.

- The MCP servers currently return mock data by default
- Session memory is in-process, not durable storage
- The frontend keeps chat history in browser local storage
- Production hardening such as auth, tenancy, and full observability is not included yet

## Prerequisites

- Python `3.11` to `3.13`
- Docker Desktop or another Docker runtime
- A valid DashScope API key

## Quick Start

### 1. Clone and enter the project

```bash
git clone <repository_url>
cd "SmartSRE Copilot Py"
```

### 2. Create a virtual environment and install dependencies

Using `uv`:

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

Using `pip`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Create `.env`

Use the included template:

```bash
cp .env.example .env
```

Then update the key fields, especially `DASHSCOPE_API_KEY`:

```env
DASHSCOPE_API_KEY=your_api_key
DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1

MILVUS_HOST=localhost
MILVUS_PORT=19530

RAG_TOP_K=3
CHUNK_MAX_SIZE=800
CHUNK_OVERLAP=100
```

### 4. Start the full stack

Linux or macOS:

```bash
make init
```

This will:
- start Milvus with Docker Compose
- start MCP services
- start FastAPI
- upload sample documents from `aiops-docs/`

### 5. Open the app

- Web UI: [http://localhost:9900](http://localhost:9900)
- API docs: [http://localhost:9900/docs](http://localhost:9900/docs)
- Health check: [http://localhost:9900/health](http://localhost:9900/health)

## Windows Startup

Use the provided scripts:

```powershell
.\start-windows.bat
.\stop-windows.bat
```

If you prefer manual startup:

1. Start Docker
2. Run `docker compose -f vector-database.yml up -d`
3. Start `mcp_servers/cls_server.py`
4. Start `mcp_servers/monitor_server.py`
5. Start `uvicorn app.main:app --host 0.0.0.0 --port 9900`
6. Upload sample documents to `/api/upload`

## Configuration

The main runtime settings live in `app/config.py`.

Key settings:

- `DASHSCOPE_API_KEY`: required
- `DASHSCOPE_API_BASE`: recommended for the compatible-mode endpoint
- `DASHSCOPE_MODEL`: chat model
- `MILVUS_HOST`, `MILVUS_PORT`: vector database connection
- `RAG_TOP_K`: retrieval count
- `CHUNK_MAX_SIZE`, `CHUNK_OVERLAP`: document chunking
- `MCP_CLS_URL`, `MCP_MONITOR_URL`: MCP service endpoints

You can start from [.env.example](/Users/mobicos/dev-sourcecode/Project-master/SmartSRE%20Copilot%20Py/.env.example).

## APIs

### Chat

`POST /api/chat`

```json
{
  "Id": "session-123",
  "Question": "What does high CPU usually indicate?"
}
```

### Streaming chat

`POST /api/chat_stream`

SSE response with incremental content messages.

### AIOps diagnosis

`POST /api/aiops`

```json
{
  "session_id": "session-123"
}
```

Returns an SSE stream with:
- planning events
- step execution events
- final diagnosis report

### Upload knowledge documents

`POST /api/upload`

- Supported by backend: `.txt`, `.md`
- Uploaded files are indexed into Milvus

### Health check

`GET /health`

Checks service and Milvus connectivity.

## Development Commands

### Service management

```bash
make init
make start
make stop
make restart
make check
```

### Docker and MCP

```bash
make up
make down
make status
make status-mcp
```

### Code quality

```bash
make format
make lint
make type-check
make security
```

### Local development

```bash
make dev
make run
make logs
```

## How AIOps Works

The diagnosis flow is built with three core nodes:

1. `Planner`
   Breaks the task into executable investigation steps and references knowledge-base experience when possible.

2. `Executor`
   Executes the current step by selecting tools and gathering evidence.

3. `Replanner`
   Decides whether to continue, adjust the remaining plan, or produce the final response.

The final output is expected to be a Markdown diagnosis report with evidence and recommendations.

## Limitations

- MCP servers are mock implementations unless you wire them to real systems
- No authentication or authorization layer
- No persistent session store
- No automated test suite is included yet
- Upload success does not always mean indexing succeeded semantically; check logs when debugging

## Troubleshooting

### FastAPI does not start

- Check whether port `9900` is already in use
- Check logs in `logs/` or `server.log`
- Verify your DashScope key is valid

### Milvus connection fails

```bash
docker compose -f vector-database.yml ps
docker compose -f vector-database.yml restart
```

### MCP tools are unavailable

- Confirm both MCP servers are running
- Check `mcp_cls.log` and `mcp_monitor.log`
- Verify MCP URLs in your environment settings

### No retrieval results

- Upload documents first
- Confirm indexing completed successfully
- Confirm Milvus is healthy

## Suggested Next Steps

If you want to evolve this project beyond demo usage, the highest-value next steps are:

1. add durable session storage
2. add auth and environment isolation
3. connect MCP tools to real observability systems
4. add tests for API and service layers
5. standardize frontend and backend validation behavior

## License

MIT
