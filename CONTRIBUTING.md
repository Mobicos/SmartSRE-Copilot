# Contributing

Thanks for contributing to SmartSRE Copilot.

## Development Setup

1. Clone the repository.
2. Create a virtual environment.
3. Install dependencies.
4. Create a local `.env`.
5. Start the required services.

Example:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
make init
```

## Branching

- Use short, descriptive branch names
- Prefer prefixes such as `feat/`, `fix/`, `docs/`, `chore/`

Examples:

- `feat/real-prometheus-mcp`
- `fix/upload-validation`
- `docs/readme-quickstart`

## Commit Style

This repository works best with conventional-style commit messages.

Examples:

- `feat: add Prometheus-backed monitor tool`
- `fix: handle missing Milvus collection gracefully`
- `docs: clarify local setup steps`
- `chore: add CI workflow`

## Pull Requests

Before opening a pull request:

- keep the scope focused
- explain why the change is needed
- include validation notes
- update documentation when setup or behavior changes

Use the PR template and include:

- summary of the change
- validation steps
- known risks

## Local Checks

Recommended commands:

```bash
make format
make lint
python -m compileall app mcp_servers
```

If a `tests/` directory exists, also run:

```bash
python -m pytest tests -q
```

## Security

- Never commit `.env`, secrets, tokens, or production credentials
- Avoid including logs that expose internal endpoints or sensitive data
- Sanitize screenshots before sharing them publicly

## Scope Notes

This repository currently mixes application code, mock MCP servers, and demo-oriented workflows.
When proposing larger changes, prefer small, reviewable pull requests over broad refactors.
