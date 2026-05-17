"""Domain models for Knowledge / Skills system."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class KnowledgeType(StrEnum):
    FAQ = "faq"
    SOP = "sop"
    INCIDENT = "incident"
    DOCUMENT = "document"
    SUMMARY = "summary"


class KnowledgeStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class KnowledgeItem:
    """A single knowledge entry in the knowledge base."""

    id: str
    knowledge_base_id: str
    item_type: KnowledgeType
    title: str
    content: str
    confidence: float
    status: KnowledgeStatus
    dedup_hash: str
    source_run_id: str | None = None
    metadata: dict[str, Any] | None = None
    created_by: str | None = None
    published_by: str | None = None


@dataclass(frozen=True)
class SkillManifest:
    """Structured SRE skill with trigger conditions, diagnostic steps, and tool requirements."""

    skill_id: str
    name: str
    description: str
    trigger_conditions: dict[str, Any]
    diagnostic_steps: list[dict[str, Any]]
    recommended_tools: list[str]
    evidence_requirements: list[str]
    risk_warnings: list[str]
    report_template: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    degradation_strategy: dict[str, Any] | None = None
    version: str = "1.0.0"


@dataclass(frozen=True)
class RetrievalScope:
    """Scoped retrieval parameters determined by scene routing."""

    item_types: list[str]
    knowledge_base_ids: list[str]
    skill_ids: list[str]
    max_items: int = 10


@dataclass(frozen=True)
class GateResult:
    """Result of the confidence gate evaluation."""

    allowed: bool
    results: list[dict[str, Any]]
    refused: bool
    best_score: float
    missing_evidence: str | None = None


@dataclass(frozen=True)
class RetrievalResult:
    """Full result from the 5-stage retrieval pipeline."""

    items: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    gate: GateResult
    query_variants: list[str]
    scope: RetrievalScope
    latency_ms: int = 0


@dataclass(frozen=True)
class CacheResult:
    """Semantic cache lookup result."""

    cached: bool
    result: dict[str, Any] | None = None
    hit_item_ids: list[str] = field(default_factory=list)
