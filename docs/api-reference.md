# API Reference

## Backend Routes

- `GET /health`: service health
- `GET /metrics`: Prometheus text-format metrics
- `POST /api/chat`: non-streaming chat
- `POST /api/chat_stream`: streaming chat via SSE
- `GET /api/chat/sessions`: persisted chat sessions
- `GET /api/chat/session/{session_id}`: session history
- `POST /api/upload`: upload and enqueue document indexing
- `GET /api/index_tasks/{task_id}`: indexing task status
- `POST /api/aiops`: streaming AIOps diagnosis via SSE
- `GET /api/aiops/runs/{run_id}`: AIOps run summary
- `GET /api/aiops/runs/{run_id}/events`: AIOps run events
- `POST /api/workspaces`: create a Native Agent workspace
- `GET /api/workspaces`: list Native Agent workspaces
- `POST /api/scenes`: create a workspace-scoped diagnosis scene
- `GET /api/scenes`: list scenes, optionally filtered by `workspace_id`
- `GET /api/scenes/{scene_id}`: fetch scene detail, linked knowledge bases, and
  tools
- `GET /api/tools`: discover diagnosis tools and persisted policies
- `PATCH /api/tools/{tool_name}/policy`: enable, disable, or require approval
  for a tool
- `POST /api/agent/runs`: run a scene-scoped Native Agent diagnosis
- `GET /api/agent/runs/{run_id}`: fetch a Native Agent run summary
- `GET /api/agent/runs/{run_id}/events`: replay a Native Agent trajectory
- `GET /api/agent/runs/{run_id}/replay`: inspect replay summary, metrics, tool
  trajectory, approvals, and final report
- `GET /api/agent/runs/{run_id}/decision-state`: inspect observations,
  decisions, evidence, handoff, recovery, and approval resume state
- `GET /api/agent/approvals`: list pending and decided approval requests
- `POST /api/agent/runs/{run_id}/approvals/{tool_name}`: approve or reject a
  pending tool call
- `POST /api/agent/runs/{run_id}/approvals/{tool_name}/resume`: resume an
  approved gated tool call
- `POST /api/agent/runs/{run_id}/feedback`: capture thumbs-up/down feedback

The frontend calls server-side handlers under `frontend/app/api/*`; browser
components should not call FastAPI directly.

## MCP Integration

MCP is optional. The application works without MCP for knowledge-base chat and
document RAG. AIOps workflows can use MCP tools when external log, metrics, and
alert systems are configured.

Recommended practices:

- Use local or internal self-hosted MCP servers for development and production.
- Treat cloud-hosted MCP SSE endpoints as quick evaluation links unless you have
  clear operational guarantees.
- Keep cloud credentials in server-side environment variables only.
- If MCP tools fail to load, the backend should report unavailable tools instead
  of inventing tool names.

Example local MCP settings:

```env
MCP_CLS_TRANSPORT=streamable-http
MCP_CLS_URL=http://localhost:8003/mcp
MCP_MONITOR_TRANSPORT=streamable-http
MCP_MONITOR_URL=http://localhost:8004/mcp
MCP_TOOLS_LOAD_TIMEOUT_SECONDS=30
```

## OpenAPI Contract

The generated FastAPI OpenAPI spec is available at:

- Runtime: `http://localhost:9900/openapi.json`
- Stored copy: `docs/openapi.json`
