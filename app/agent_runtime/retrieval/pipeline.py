"""Retrieval pipeline — 5-stage assembly: rewrite → route → recall → rerank → gate."""

from __future__ import annotations

import time
from typing import Any, Protocol

from app.agent_runtime.knowledge_types import GateResult, RetrievalResult
from app.agent_runtime.retrieval.confidence_gate import ConfidenceGate
from app.agent_runtime.retrieval.query_rewriter import QueryRewriter
from app.agent_runtime.retrieval.reranker import Reranker
from app.agent_runtime.retrieval.scene_router import SceneRouter
from app.agent_runtime.retrieval.semantic_cache import SemanticCache


class _KnowledgeSearcher(Protocol):
    def search_knowledge(
        self, *, workspace_id: str, query: str, item_type: str | None = None, top_k: int = 5
    ) -> list[dict[str, Any]]: ...


class RetrievalPipeline:
    """5-stage retrieval pipeline for the knowledge system.

    Stages:
        1. Query Rewrite — expand goal into multiple query variants
        2. Scene Route — classify intent and scope retrieval
        3. Vector Recall — search knowledge base with rewritten queries
        4. Rerank (optional) — Cross-Encoder precision ranking
        5. Confidence Gate — enforce minimum quality threshold

    Usage::

        pipeline = RetrievalPipeline(
            rewriter=QueryRewriter(),
            router=SceneRouter(),
            knowledge_searcher=knowledge_service,
            gate=ConfidenceGate(threshold=0.6),
        )
        result = pipeline.retrieve(
            workspace_id="ws-1", goal="CPU high", scene={}, kb_id="kb-1"
        )
        if result.gate.refused:
            # inject missing_evidence into decision context
    """

    def __init__(
        self,
        *,
        rewriter: QueryRewriter | None = None,
        router: SceneRouter | None = None,
        knowledge_searcher: _KnowledgeSearcher | None = None,
        gate: ConfidenceGate | None = None,
        reranker: Reranker | None = None,
        cache: SemanticCache | None = None,
    ) -> None:
        self._rewriter = rewriter or QueryRewriter()
        self._router = router or SceneRouter()
        self._searcher = knowledge_searcher
        self._gate = gate or ConfidenceGate()
        self._reranker = reranker or Reranker(enabled=False)
        self._cache = cache

    def retrieve(
        self,
        *,
        workspace_id: str,
        goal: str,
        scene: dict[str, Any],
        kb_id: str,
    ) -> RetrievalResult:
        """Execute the full 5-stage retrieval pipeline."""
        start = time.monotonic()

        # Stage 1: Query rewrite
        query_variants = self._rewriter.rewrite(goal, scene=scene)

        # Stage 2: Scene routing
        scope = self._router.route(goal, scene=scene)

        # Stage 0 (bonus): Semantic cache check
        if self._cache is not None:
            cached = self._cache.lookup(workspace_id=workspace_id, query=goal)
            if cached is not None and cached.result is not None:
                elapsed = int((time.monotonic() - start) * 1000)
                return RetrievalResult(
                    items=[cached.result],
                    citations=[],
                    gate=GateResult(
                        allowed=True,
                        results=[cached.result],
                        refused=False,
                        best_score=cached.result.get("score", 1.0),
                    ),
                    query_variants=query_variants,
                    scope=scope,
                    latency_ms=elapsed,
                )

        # Stage 3: Vector recall
        all_items: list[dict[str, Any]] = []
        if self._searcher is not None:
            for q in query_variants[:3]:
                try:
                    items = self._searcher.search_knowledge(
                        workspace_id=workspace_id,
                        query=q,
                        item_type=scope.item_types[0] if len(scope.item_types) == 1 else None,
                        top_k=scope.max_items,
                    )
                    all_items.extend(items)
                except Exception:
                    pass

        # Deduplicate by content
        seen_contents: set[str] = set()
        unique_items: list[dict[str, Any]] = []
        for item in all_items:
            content = item.get("content", "")
            if content not in seen_contents:
                seen_contents.add(content)
                unique_items.append(item)

        # Stage 4: Rerank (optional)
        if self._reranker.is_available and unique_items:
            unique_items = self._reranker.rerank(goal, unique_items, top_k=scope.max_items)

        # Stage 5: Confidence gate
        gate_result = self._gate.evaluate(unique_items)

        # Build citations from allowed results
        citations = [
            {
                "content": r.get("content", ""),
                "score": r.get("score", r.get("rerank_score", 0.0)),
                "source": r.get("metadata", {}).get("source", "knowledge"),
            }
            for r in gate_result.results
        ]

        # Cache high-confidence results
        if self._cache is not None and gate_result.allowed and gate_result.best_score >= 0.8:
            self._cache.store(
                workspace_id=workspace_id,
                query=goal,
                result={"items": gate_result.results, "score": gate_result.best_score},
            )

        elapsed = int((time.monotonic() - start) * 1000)
        return RetrievalResult(
            items=gate_result.results,
            citations=citations,
            gate=gate_result,
            query_variants=query_variants,
            scope=scope,
            latency_ms=elapsed,
        )
