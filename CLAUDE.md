# SmartSRE-Copilot

All development conventions are in `CONTRIBUTING.md` and `AGENTS.md`. Read them
before committing, creating PRs, or making architectural changes.

## PR Creation

This is the only Claude Code-specific rule. When creating a pull request with
`gh pr create`:

### Step 1: Read the diff

```bash
git diff main...HEAD --stat
git diff main...HEAD
git log main...HEAD --oneline
```

### Step 2: Write the body from the diff

NEVER copy `.github/pull_request_template.md` verbatim. Every section must
contain content derived from the actual changes.

**Summary** — 2-3 sentences naming the specific problem or feature:
- Good: "Add HMAC-based API key fingerprinting to replace plaintext key
  prefixes in audit logs"
- Bad: "Improve security" / "Harden runtime"

**Changes** — bullet list, each referencing a specific file or function:
- Good: "`app/security/auth.py` — replace `x_api_key[:8]` subject with HMAC
  fingerprint"
- Bad: "Updated auth module"

**Validation** — only check `[x]` for checks actually run.

**Risks** — concrete risk of THIS change:
- Good: "Low — auth subject identifiers change format; existing audit logs
  retain old format"
- Bad: "Operational risk: none"

If a section does not apply, write "N/A — ..." not the template placeholder.

## Project Structure

```
app/agent_runtime/    Native Agent core
app/application/      Business services
app/api/              FastAPI routes
app/domains/          Schemas, entities
app/infrastructure/   Tool registry, MCP, Redis
app/platform/         Database, repositories
app/security/         Auth, rate limiting
app/observability/    Metrics, tracing
frontend/             Next.js + Zustand
tests/                pytest + Playwright
docs/                 Architecture, workflow, security
```
