"""PostgreSQL schema facade.

Table classes live in domain modules under ``app.platform.persistence.tables``.
This facade keeps existing imports stable and exposes ``REQUIRED_TABLES`` from
SQLModel metadata so table discovery does not need manual maintenance.
"""

from __future__ import annotations

from sqlmodel import SQLModel

from app.platform.persistence.tables import (
    AgentCheckpoint,
    AgentCheckpointBlob,
    AgentCheckpointWrite,
    AgentEvent,
    AgentFeedback,
    AgentMemory,
    AgentRun,
    AIOpsRun,
    AIOpsRunEvent,
    AnalyticsFindingTable,
    AuditLog,
    ChatToolEvent,
    IncidentLinkTable,
    IncidentTable,
    IndexingTask,
    KnowledgeAuditLogTable,
    KnowledgeBase,
    KnowledgeItemTable,
    Message,
    Scene,
    SceneKnowledgeBase,
    SceneTool,
    Session,
    SkillManifestTable,
    ToolPolicy,
    Workspace,
)

REQUIRED_TABLES = tuple(SQLModel.metadata.tables.keys())

__all__ = [
    "AIOpsRun",
    "AIOpsRunEvent",
    "AgentCheckpoint",
    "AgentCheckpointBlob",
    "AgentCheckpointWrite",
    "AgentEvent",
    "AgentFeedback",
    "AgentMemory",
    "AgentRun",
    "AnalyticsFindingTable",
    "AuditLog",
    "ChatToolEvent",
    "IncidentLinkTable",
    "IncidentTable",
    "IndexingTask",
    "KnowledgeAuditLogTable",
    "KnowledgeBase",
    "KnowledgeItemTable",
    "Message",
    "REQUIRED_TABLES",
    "Scene",
    "SceneKnowledgeBase",
    "SceneTool",
    "Session",
    "SkillManifestTable",
    "ToolPolicy",
    "Workspace",
]
