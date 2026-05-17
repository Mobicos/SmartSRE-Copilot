# Troubleshooting

## Backend cannot start

- Check `PORT` availability.
- Verify `.env` values.
- Ensure PostgreSQL and Milvus are reachable.
- Run `uv run alembic upgrade head`.

## Upload succeeds but indexing never completes

- Check `TASK_DISPATCHER_MODE`.
- If `detached`, start `uv run python -m app.worker`.
- Check Redis connectivity and task status endpoint.

## MCP tools unavailable

- Confirm MCP URL and transport are correct.
- Increase `MCP_TOOLS_LOAD_TIMEOUT_SECONDS` if tool discovery is slow.
- Test the MCP server independently before blaming the Agent.
- Remember that Tencent CLS MCP queries Tencent CLS data, not local app data.

## Frontend cannot reach backend

- Check `frontend/.env.local`.
- Ensure `SMARTSRE_BACKEND_URL` points to the FastAPI service.
- If backend auth is enabled, set `SMARTSRE_API_KEY` server-side only.

## SSE streaming issues

- Streaming endpoints (`/api/chat_stream`, `/api/aiops`, `/api/agent/runs/stream`)
  use Server-Sent Events. Ensure no reverse proxy or CDN buffers SSE responses.
- In Nginx, set `proxy_buffering off` and `X-Accel-Buffering: no`.
- In Caddy, no special configuration is needed for SSE by default.
- If the browser shows no incremental updates, check the browser DevTools Network
  tab for `text/event-stream` responses. A `502` or `504` status usually means
  the backend is unreachable or timed out.
- The BFF layer uses a 30-second timeout (`SMARTSRE_BACKEND_TIMEOUT_MS`). For
  long-running diagnoses, consider increasing this value in `frontend/.env.local`.
- If MCP tool discovery is slow, increase `MCP_TOOLS_LOAD_TIMEOUT_SECONDS`.

## Docker proxy errors

If Docker fails with a proxy error such as `127.0.0.1:7890 refused`, start the
local proxy configured in Docker Desktop, or clear Docker Desktop proxy settings
and retry a direct image pull such as `docker pull pgvector/pgvector:pg16`.
After image pulls work, rerun the smoke script.
