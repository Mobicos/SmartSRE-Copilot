"""Native Agent persistence tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Workspace(SQLModel, table=True):
    __tablename__ = "workspaces"

    workspace_id: str = Field(primary_key=True)
    name: str
    description: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class KnowledgeBase(SQLModel, table=True):
    __tablename__ = "knowledge_bases"

    knowledge_base_id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspaces.workspace_id", ondelete="CASCADE")
    name: str
    description: str | None = None
    version: str = Field(default="0.0.1")
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class Scene(SQLModel, table=True):
    __tablename__ = "scenes"

    scene_id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspaces.workspace_id", ondelete="CASCADE")
    name: str
    description: str | None = None
    agent_config: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class SceneKnowledgeBase(SQLModel, table=True):
    __tablename__ = "scene_knowledge_bases"

    scene_id: str = Field(foreign_key="scenes.scene_id", ondelete="CASCADE", primary_key=True)
    knowledge_base_id: str = Field(
        foreign_key="knowledge_bases.knowledge_base_id", ondelete="CASCADE", primary_key=True
    )


class SceneTool(SQLModel, table=True):
    __tablename__ = "scene_tools"

    scene_id: str = Field(foreign_key="scenes.scene_id", ondelete="CASCADE", primary_key=True)
    tool_name: str = Field(primary_key=True)


class ToolPolicy(SQLModel, table=True):
    __tablename__ = "tool_policies"

    tool_name: str = Field(primary_key=True)
    scope: str = Field(default="diagnosis")
    risk_level: str = Field(default="low")
    capability: str | None = None
    enabled: bool = Field(default=True)
    approval_required: bool = Field(default=False)
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"

    run_id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspaces.workspace_id", ondelete="CASCADE")
    scene_id: str | None = Field(
        sa_column=sa.Column(
            sa.Text, sa.ForeignKey("scenes.scene_id", ondelete="SET NULL"), nullable=True
        )
    )
    session_id: str
    status: str
    goal: str
    final_report: str | None = None
    error_message: str | None = None
    runtime_version: str | None = None
    trace_id: str | None = None
    model_name: str | None = None
    decision_provider: str | None = None
    step_count: int | None = None
    tool_call_count: int | None = None
    latency_ms: int | None = None
    error_type: str | None = None
    approval_state: str | None = None
    retrieval_count: int | None = None
    cost_estimate: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
    )
    handoff_reason: str | None = None
    token_usage: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
    )
    recovery_count: int | None = Field(
        default=0,
        sa_column=sa.Column(sa.Integer, nullable=True),
    )
    empty_result_count: int | None = Field(
        default=0,
        sa_column=sa.Column(sa.Integer, nullable=True),
    )
    duplicate_tool_call_count: int | None = Field(
        default=0,
        sa_column=sa.Column(sa.Integer, nullable=True),
    )
    step_latencies: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
    )
    regression_score: float | None = Field(
        default=None,
        sa_column=sa.Column(sa.Float, nullable=True),
    )
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class AgentEvent(SQLModel, table=True):
    __tablename__ = "agent_events"
    __table_args__ = (sa.Index("idx_agent_events_run_created", "run_id", "created_at", "id"),)

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    run_id: str = Field(foreign_key="agent_runs.run_id", ondelete="CASCADE")
    event_type: str
    stage: str
    message: str
    payload: str | None = None
    step_index: int | None = None
    evidence_quality: str | None = None
    recovery_action: str | None = None
    token_usage: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
    )
    cost_estimate: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
    )
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class AgentFeedback(SQLModel, table=True):
    __tablename__ = "agent_feedback"

    feedback_id: str = Field(primary_key=True)
    run_id: str = Field(foreign_key="agent_runs.run_id", ondelete="CASCADE")
    rating: str
    comment: str | None = None
    correction: str | None = None
    badcase_flag: bool = Field(default=False)
    original_report: str | None = None
    review_status: str = Field(default="pending")
    review_note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=True),
    )
    knowledge_status: str = Field(default="not_promoted")
    knowledge_task_id: str | None = None
    knowledge_filename: str | None = None
    promoted_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=True),
    )
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class AgentMemory(SQLModel, table=True):
    __tablename__ = "agent_memory"

    memory_id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspaces.workspace_id", ondelete="CASCADE")
    run_id: str | None = Field(foreign_key="agent_runs.run_id", ondelete="SET NULL")
    conclusion_text: str
    conclusion_type: str = Field(default="final_report")
    confidence: float = Field(default=0.5)
    validation_count: int = Field(default=0)
    memory_metadata: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column("metadata", sa.JSON, nullable=True),
    )
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class KnowledgeItemTable(SQLModel, table=True):
    __tablename__ = "knowledge_items"

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    knowledge_base_id: str = Field(
        foreign_key="knowledge_bases.knowledge_base_id", ondelete="CASCADE"
    )
    item_type: str
    title: str
    content: str
    confidence: float = Field(default=0.5)
    source_run_id: str | None = Field(
        sa_column=sa.Column(
            sa.Text, sa.ForeignKey("agent_runs.run_id", ondelete="SET NULL"), nullable=True
        )
    )
    status: str = Field(default="draft")
    dedup_hash: str | None = None
    item_metadata: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column("metadata", sa.JSON, nullable=True),
    )
    created_by: str | None = None
    published_by: str | None = None
    published_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=True),
    )
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class SkillManifestTable(SQLModel, table=True):
    __tablename__ = "skill_manifests"

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    skill_id: str = Field(unique=True)
    name: str
    description: str | None = None
    trigger_conditions: dict[str, Any] = Field(
        sa_column=sa.Column(sa.JSON, nullable=False),
    )
    diagnostic_steps: dict[str, Any] = Field(
        sa_column=sa.Column(sa.JSON, nullable=False),
    )
    recommended_tools: dict[str, Any] = Field(
        sa_column=sa.Column(sa.JSON, nullable=False),
    )
    evidence_requirements: dict[str, Any] = Field(
        sa_column=sa.Column(sa.JSON, nullable=False),
    )
    risk_warnings: dict[str, Any] = Field(
        sa_column=sa.Column(sa.JSON, nullable=False),
    )
    report_template: str | None = None
    input_schema: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
    )
    output_schema: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
    )
    degradation_strategy: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
    )
    version: str = Field(default="1.0.0")
    status: str = Field(default="active")
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class KnowledgeAuditLogTable(SQLModel, table=True):
    __tablename__ = "knowledge_audit_log"
    __table_args__ = (sa.Index("idx_kal_item", "item_id", "created_at"),)

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    item_id: int = Field(foreign_key="knowledge_items.id", ondelete="CASCADE")
    action: str
    actor: str | None = None
    audit_details: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column("details", sa.JSON, nullable=True),
    )
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class IncidentTable(SQLModel, table=True):
    __tablename__ = "incidents"

    incident_id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspaces.workspace_id", ondelete="CASCADE")
    title: str
    severity: str = Field(default="P2")
    service_name: str | None = None
    owner: str | None = None
    status: str = Field(default="open")
    source: str = Field(default="manual")
    summary: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    resolved_at: datetime | None = Field(
        default=None, sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=True)
    )


class IncidentLinkTable(SQLModel, table=True):
    __tablename__ = "incident_links"

    link_id: str = Field(primary_key=True)
    incident_id: str = Field(foreign_key="incidents.incident_id", ondelete="CASCADE")
    target_type: str
    target_id: str
    relationship: str
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class AnalyticsFindingTable(SQLModel, table=True):
    __tablename__ = "analytics_findings"

    finding_id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspaces.workspace_id", ondelete="CASCADE")
    category: str
    title: str
    summary: str
    evidence_refs: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=sa.Column(sa.JSON, nullable=False),
    )
    status: str = Field(default="open")
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
