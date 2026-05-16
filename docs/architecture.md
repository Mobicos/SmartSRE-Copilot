# Architecture

SmartSRE Copilot is an SRE Agent workbench with a FastAPI backend, Next.js BFF
frontend, PostgreSQL persistence, Redis-backed tasks, vector search, and
optional MCP tool integrations.

## Current Development Baseline

```text
Browser
  -> Next.js BFF
  -> FastAPI
      -> PostgreSQL
      -> Redis
      -> Milvus
      -> DashScope / Qwen
      -> MCP servers
```

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

## Development Direction

- Move the platform middleware toward PostgreSQL + pgvector, Redis, MinIO,
  Caddy, and OpenTelemetry.
- Stabilize knowledge indexing, replay snapshots, and AgentOps metrics.
- Harden tool governance, approval flows, and API contracts.
- Introduce Decision Runtime contracts, deterministic providers, and LangGraph
  runtime hardening.
- Enable the native Agent decision runtime by default when the product and
  validation scope is complete.
