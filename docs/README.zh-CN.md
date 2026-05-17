# SmartSRE Copilot

> 面向 SRE 的智能运维助手，支持知识库问答、AIOps 诊断和原生 Agent 工作台。

[English](../README.md) | [简体中文](README.zh-CN.md)

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic-orange.svg)](https://www.langchain.com/langgraph)
[![Next.js](https://img.shields.io/badge/Next.js-Frontend-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](../LICENSE)
[![CI](https://github.com/Mobicos/SmartSRE-Copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/Mobicos/SmartSRE-Copilot/actions/workflows/ci.yml)

## 项目概览

SmartSRE Copilot 当前是开发阶段的 Native Agent Workbench，面向企业内部运维场景构建智能助手。后端基于
FastAPI、LangChain/LangGraph、DashScope/Qwen、PostgreSQL、Redis 和 Milvus；前端基于
Next.js，通过服务端 BFF 路由访问后端，避免把后端密钥暴露到浏览器。

核心能力：

- 基于上传 `.txt` 和 `.md` 文档的知识库问答。
- 流式对话和会话历史持久化。
- 支持失败重试的后台异步索引流水线。
- Planner / Executor / Replanner 模式的 AIOps 诊断流程。
- Native Agent 工作空间、场景、工具策略、轨迹回放和反馈 API。
- 可选 MCP 工具接入外部日志、指标和告警系统。

## 项目状态

**开发阶段** — 除版本号、tag 和 release 制品外，2.0 生产能力已按主路径实现。上线前必须完成质量门、
浏览器 E2E、Compose smoke、真实 Qwen key 和生产密钥验证。

## 架构

```text
浏览器
  |
  v
Next.js 前端 (BFF 服务端路由)
  |
  v
FastAPI 后端
  |
  +-- 对话 / RAG ----------------> Qwen + MCP 工具
  +-- 上传 / 索引 ---------------> Redis + DashScope Embedding
  +-- Native Agent 诊断 ---------> AgentRuntime + ToolPolicy
  +-- Decision Runtime ----------> LangGraph StateGraph
  +-- Checkpoint Resume ----------> 审批门 + 自动恢复
  +-- 持久化 --------------------> PostgreSQL + pgvector
```

完整架构详情：[docs/architecture.md](architecture.md)

## 快速开始

### 前置要求

- Python `3.11+`、`uv`、Docker、Node.js + `pnpm`、DashScope API key

### 1. 后端环境

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
cp .env.example .env    # 设置 DASHSCOPE_API_KEY 和 APP_API_KEY
```

### 2. 启动基础设施

```bash
# 完整 Docker 栈（推荐）
docker compose up -d --build

# 或本地开发模式——仅启动基础设施
cp docker-compose.yml docker-compose.local.yml
docker compose -f docker-compose.local.yml up -d postgres redis standalone attu minio
```

### 3. 数据库迁移与启动

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 9900
```

### 4. 启动前端

```bash
cd frontend
pnpm install --frozen-lockfile
cp .env.example .env.local
pnpm dev
```

### 服务地址

- 前端：http://localhost:3000
- 后端 API：http://localhost:9900
- API 文档：http://localhost:9900/docs

完整部署指南：[docs/deployment.md](deployment.md)

## 文档

| 文档 | 说明 |
|------|------|
| [docs/architecture.md](architecture.md) | 系统架构、技术栈、数据边界 |
| [docs/deployment.md](deployment.md) | 完整部署指南、配置、Compose Profile |
| [docs/api-reference.md](api-reference.md) | 后端 API 路由、MCP 接入 |
| [docs/development-workflow.md](development-workflow.md) | 分支流程、提交格式、PR 规则 |
| [docs/troubleshooting.md](troubleshooting.md) | 常见问题与解决方案 |
| [docs/repository-governance.md](repository-governance.md) | 分支保护、标签、维护者规则 |
| [docs/security.md](security.md) | 运维安全检查清单 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 人类贡献者工作流 |
| [AGENTS.md](../AGENTS.md) | AI 编码 Agent 执行规则 |
| [SECURITY.md](../SECURITY.md) | 漏洞报告策略 |

## 贡献

请先阅读 `CONTRIBUTING.md` 了解贡献流程、提交格式、分支策略、PR 规则和质量门。AI 编码 Agent 还应在改动前阅读 `AGENTS.md`。

开发阶段不要创建公开交付 tag、GitHub 交付制品或容器分发自动化。

## 许可证

Apache License 2.0。详见 [LICENSE](../LICENSE)。
