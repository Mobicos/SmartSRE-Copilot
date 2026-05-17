# Architecture

SmartSRE Copilot is an SRE Agent workbench with a FastAPI backend, Next.js BFF
frontend, PostgreSQL persistence, Redis-backed tasks, vector search, and
optional MCP tool integrations.

## System Overview

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
  |                                + pgvector (default) / Milvus (optional)
  |
  +-- Native Agent diagnosis ----> AgentRuntime
  |                                + ToolCatalog / ToolPolicy / ToolExecutor
  |                                + trajectory events
  |                                + optional MCP tools
  |
  +-- Decision Runtime ----------> LangGraph StateGraph
  |                                + deterministic / LLM routing
  |                                + step-by-step execution
  |                                + evidence-driven synthesis
  |
  +-- Checkpoint Resume ---------> DatabaseCheckpointSaver
  |                                + approval gate per high-risk step
  |                                + auto-resume after approval
  |
  +-- Approval Workflow ---------> agent_events table
  |                                + approval_required flag per tool
  |                                + UI approval queue
  |
  +-- Persistence ---------------> PostgreSQL
```

## Middleware Architecture

```text
Internet
  |
  v
Caddy reverse proxy (TLS, static assets, /api proxy)
  |
  +-- / ------------> Next.js frontend (SSR + BFF route handlers)
  |
  +-- /api ---------> FastAPI backend
                        |
                        +-- OpenTelemetry SDK ---> OTel Collector ---> Prometheus / Loki
                        |
                        +-- PostgreSQL (persistence + pgvector)
                        +-- Redis (task queue + cache)
```

- **Caddy** — TLS termination, automatic HTTPS, static asset serving, reverse
  proxy to backend and frontend. Deployed via `docker compose --profile gateway up`.
- **Next.js BFF** — Server-side route handlers in `frontend/app/api/` that call
  the FastAPI backend, keeping API keys and internal URLs off the client.
- **FastAPI** — Core business logic, LangGraph agents, vector search, persistence.
- **Observability** — OpenTelemetry SDK (conditional via `OTEL_ENABLED`) exports
  traces to OTel Collector; Prometheus scrapes `/metrics`; Loki collects logs.
  Deployed via `docker compose --profile observability up`.

## Tech Stack

**Backend:**
- FastAPI, Pydantic Settings, Server-Sent Events
- LangChain, LangGraph, Qwen via DashScope
- PostgreSQL (with pgvector), Alembic, Redis
- MCP client support for external tool servers
- Native Agent runtime, tool policy, scene, and trajectory persistence

**Frontend:**
- Next.js, React, TypeScript
- Server-side API route handlers as a BFF layer
- pnpm lockfile committed for reproducible frontend installs

## Repository Layout

```text
app/              FastAPI backend, agents, services, persistence
alembic/          PostgreSQL schema migrations
frontend/         Next.js frontend application
mcp_servers/      Local/mock MCP server examples
tests/            Backend tests
docs/             All project documentation
scripts/          Operational scripts and utilities
config/           Infrastructure configs (otel, prometheus)
```

## Data Ownership

Local application data stays local unless you explicitly connect external tools.

- Uploaded files are stored under `uploads/`.
- Chat history, task status, audit logs, and AIOps run events are stored in
  PostgreSQL.
- Native Agent workspaces, scenes, tool policies, trajectories, and feedback are
  stored in PostgreSQL.
- Document vectors are stored in pgvector (default) or Milvus (optional).
- DashScope receives prompts and embedding inputs required for model calls.
- MCP tools are optional. A Tencent Cloud CLS MCP server queries Tencent CLS
  data, not local Postgres or Milvus data.

## Core Boundaries

- Browser components call Next.js route handlers, not FastAPI directly.
- FastAPI owns authentication, persistence, Agent runtime, and tool governance.
- PostgreSQL is the system of record for runs, events, feedback, tasks, and
  policies.
- Redis is for background queues and short-lived state.
- Tool execution must go through ToolPolicyGate and ToolExecutor.
- MCP is the standard integration boundary for external observability systems.

## Native Agent Workbench

```text
Workspace
  -> Scene
  -> Goal
  -> Tool Policy
  -> Agent Runtime (BoundedReActLoop)
      -> observe (MemoryRetriever injects historical context)
      -> decide (DeterministicDecisionProvider / QwenDecisionProvider)
          -> InterventionBridge checks for human interventions
      -> act (ToolExecutor with policy gate)
      -> assess (EvidenceAssessor)
  -> Final Report
  -> MemoryExtractor (persists conclusions to pgvector)
  -> Feedback
  -> Replayable Events
```

### Proactive Monitoring

`ProactiveMonitor` periodically probes service metrics via `MetricProvider`,
deduplicates alerts with `AlertDeduplicator` (time-window suppression),
and auto-triggers `AutoDiagnosisTrigger` to create an AgentRun on anomaly.

### Cross-session Memory

Conclusions from previous runs are embedded via DashScope text-embedding-v4
and stored in `agent_memory` with pgvector HNSW indexing. On each new run,
`MemoryRetriever` retrieves similar historical conclusions and injects them
as context into the first loop step.

### Collaborative Intervention

`InterventionBridge` allows human operators to intervene during an agent run:
- **inject_evidence**: append observation before the decide step
- **replace_tool_call**: override decision after the decide step
- **modify_goal**: update the run goal contract

Low-confidence auto-handoff pauses the loop after N consecutive low-confidence
decisions, emitting a `human_handoff` event for operator response.

## Operational Flows

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
  -> compatibility wrapper
  -> AgentRuntime
  -> ToolExecutor
  -> persisted Native Agent trajectory + AIOps-compatible run events
```

Native Agent development runtime:

```text
Workspace
  -> Scene
  -> Knowledge bases + MCP/local tools
  -> AgentRuntime
  -> Tool policy checks
  -> Tool calls and results
  -> Trajectory replay
  -> Feedback and analytics inputs
```

## Agent Workbench User Guide

The Agent Workbench at `/agent` provides an interactive interface for
running SRE diagnoses:

1. **Create a Workspace**: Go to `/agent` and create a workspace (e.g. "SRE-Team").
2. **Create a Scene**: Within the workspace, create a scene that selects which
   tools and knowledge bases are available for diagnosis runs.
3. **Run a Diagnosis**: Enter a goal (e.g. "Diagnose latency spike on /api/orders")
   and start a run. The Agent will plan tool calls, collect evidence, and produce
   a final report.
4. **Review Approvals**: High-risk tools require explicit approval before execution.
   Visit `/agent/approvals` to approve or reject pending actions.
5. **Replay Runs**: Visit `/agent/history` to browse past runs. Click a run to see
   the full trajectory, tool calls, evidence, and final report.
6. **Manage Tools**: Visit `/agent/tools` to view available tools, their risk levels,
   and policy configurations. Use `PATCH /api/tools/{tool_name}/policy` to adjust
   tool governance settings.
7. **Feedback**: After reviewing a run, submit thumbs-up/down feedback to help
   improve the Agent's performance over time.

## Development Direction

- Move the platform middleware toward PostgreSQL + pgvector, Redis, MinIO,
  Caddy, and OpenTelemetry.
- Stabilize knowledge indexing, replay snapshots, and AgentOps metrics.
- Harden tool governance, approval flows, and API contracts.
- Introduce Decision Runtime contracts, deterministic providers, and LangGraph
  runtime hardening.
- Enable the native Agent decision runtime by default when the product and
  validation scope is complete.
