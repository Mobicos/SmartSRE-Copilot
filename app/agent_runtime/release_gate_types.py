"""Typed response schema for release gate metrics."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GateThresholds(BaseModel):
    goal_completion_rate_min: float = 0.80
    unnecessary_tool_call_ratio_max: float = 0.10
    approval_override_rate_max: float = 0.05
    p95_latency_ms_max: int = 60000


class ReleaseGateResult(BaseModel):
    """Typed response for the /agent/metrics/release-gate endpoint."""

    window_size: int = 0
    completed_runs: int = 0
    goal_completion_rate: float = 0.0
    unnecessary_tool_call_ratio: float = 0.0
    approval_override_rate: float = 0.0
    p95_latency_ms: int | None = None
    handoff_rate: float = 0.0
    approval_wait_time_p50_ms: int | None = None
    approval_wait_time_p95_ms: int | None = None
    gate_pass: bool = False
    gate_thresholds: GateThresholds = Field(default_factory=GateThresholds)


class KnowledgeGateThresholds(BaseModel):
    faq_knowledge_ratio_min: float = 0.50
    retrieval_recall_at_5_min: float = 0.85
    low_confidence_refusal_rate_min: float = 1.0
    knowledge_dedup_usable: bool = True
    has_dynamic_tool_scenario: bool = True


class KnowledgeGateResult(BaseModel):
    """Typed response for the knowledge release gate."""

    faq_knowledge_ratio: float = 0.0
    retrieval_recall_at_5: float | None = None
    low_confidence_refusal_rate: float = 1.0
    knowledge_dedup_usable: bool = True
    has_dynamic_tool_scenario: bool = False
    interception_rate: float = 0.0
    faq_hit_rate: float = 0.0
    rerank_precision: float | None = None
    rerank_recall: float | None = None
    gate_pass: bool = False
    gate_thresholds: KnowledgeGateThresholds = Field(default_factory=KnowledgeGateThresholds)
    total_runs_evaluated: int = 0
