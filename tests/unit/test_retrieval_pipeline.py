"""Unit tests for retrieval pipeline (query rewrite, scene route, gate, rerank, cache)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.agent_runtime.knowledge_types import RetrievalResult
from app.agent_runtime.retrieval.confidence_gate import ConfidenceGate
from app.agent_runtime.retrieval.pipeline import RetrievalPipeline
from app.agent_runtime.retrieval.query_rewriter import QueryRewriter
from app.agent_runtime.retrieval.reranker import Reranker
from app.agent_runtime.retrieval.scene_router import SceneRouter
from app.agent_runtime.retrieval.semantic_cache import SemanticCache

# ---------------------------------------------------------------------------
# QueryRewriter
# ---------------------------------------------------------------------------


def test_query_rewriter_returns_original():
    rewriter = QueryRewriter()
    variants = rewriter.rewrite("CPU 使用率过高")
    assert variants[0] == "CPU 使用率过高"


def test_query_rewriter_extracts_aliases():
    rewriter = QueryRewriter()
    variants = rewriter.rewrite("CPU高负载，使用率95%")
    assert any("cpu_high" in v for v in variants)


def test_query_rewriter_includes_scene_context():
    rewriter = QueryRewriter()
    variants = rewriter.rewrite("内存增长", scene={"description": "production server"})
    assert any("production server" in v for v in variants)


def test_query_rewriter_extracts_english_tokens():
    rewriter = QueryRewriter()
    variants = rewriter.rewrite("CPU usage is high on web-01")
    assert any("CPU" in v and "usage" in v for v in variants)


# ---------------------------------------------------------------------------
# SceneRouter
# ---------------------------------------------------------------------------


def test_scene_router_investigative_scope():
    router = SceneRouter()
    scope = router.route("为什么 CPU 使用率这么高", scene={})
    assert "incident" in scope.item_types
    assert "document" in scope.item_types


def test_scene_router_procedural_scope():
    router = SceneRouter()
    scope = router.route("CPU 高排查步骤怎么做", scene={})
    assert scope.item_types == ["faq", "sop"]


def test_scene_router_default_scope():
    router = SceneRouter()
    scope = router.route("CPU 高负载", scene={})
    assert "faq" in scope.item_types
    assert "sop" in scope.item_types


def test_scene_router_uses_scene_kb_ids():
    router = SceneRouter()
    scope = router.route("test", scene={"knowledge_base_ids": ["kb-1", "kb-2"]})
    assert scope.knowledge_base_ids == ["kb-1", "kb-2"]


# ---------------------------------------------------------------------------
# ConfidenceGate
# ---------------------------------------------------------------------------


def test_confidence_gate_pass():
    gate = ConfidenceGate(threshold=0.5)
    results = [{"content": "a", "score": 0.8}, {"content": "b", "score": 0.6}]
    result = gate.evaluate(results)
    assert result.allowed is True
    assert result.refused is False
    assert result.best_score == 0.8


def test_confidence_gate_refuse():
    gate = ConfidenceGate(threshold=0.7)
    results = [{"content": "a", "score": 0.3}, {"content": "b", "score": 0.5}]
    result = gate.evaluate(results)
    assert result.allowed is False
    assert result.refused is True
    assert result.missing_evidence is not None


def test_confidence_gate_refuse_empty():
    gate = ConfidenceGate()
    result = gate.evaluate([])
    assert result.refused is True
    assert result.best_score == 0.0


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------


def test_reranker_graceful_degradation():
    reranker = Reranker(enabled=False)
    results = [{"content": "a", "score": 0.5}, {"content": "b", "score": 0.8}]
    reranked = reranker.rerank("query", results, top_k=5)
    assert len(reranked) == 2
    assert reranked[0]["content"] == "a"


def test_reranker_with_provider():
    mock_provider = MagicMock()
    mock_provider.rerank.return_value = [(1, 0.9), (0, 0.7)]
    reranker = Reranker(model_provider=mock_provider)
    results = [{"content": "a", "score": 0.5}, {"content": "b", "score": 0.8}]
    reranked = reranker.rerank("query", results, top_k=2)
    assert len(reranked) == 2
    assert reranked[0]["content"] == "b"
    assert reranked[0]["rerank_score"] == 0.9


def test_reranker_empty_results():
    reranker = Reranker(model_provider=MagicMock())
    assert reranker.rerank("q", [], top_k=5) == []


# ---------------------------------------------------------------------------
# SemanticCache
# ---------------------------------------------------------------------------


def test_semantic_cache_store_and_lookup():
    cache = SemanticCache()
    cache.store(workspace_id="ws-1", query="CPU high", result={"score": 0.95}, item_ids=["1"])
    hit = cache.lookup(workspace_id="ws-1", query="CPU high")
    assert hit is not None
    assert hit.cached is True
    assert hit.result is not None


def test_semantic_cache_miss():
    cache = SemanticCache()
    hit = cache.lookup(workspace_id="ws-1", query="unknown")
    assert hit is None


def test_semantic_cache_clear():
    cache = SemanticCache()
    cache.store(workspace_id="ws-1", query="q", result={"score": 1.0})
    cache.clear()
    assert cache.lookup(workspace_id="ws-1", query="q") is None


# ---------------------------------------------------------------------------
# RetrievalPipeline — full e2e
# ---------------------------------------------------------------------------


def test_pipeline_e2e_with_searcher():
    mock_searcher = MagicMock()
    mock_searcher.search_knowledge.return_value = [
        {"content": "Check load average", "score": 0.85},
        {"content": "Check process list", "score": 0.70},
    ]

    pipeline = RetrievalPipeline(
        knowledge_searcher=mock_searcher,
        gate=ConfidenceGate(threshold=0.5),
    )
    result = pipeline.retrieve(
        workspace_id="ws-1",
        goal="CPU 高负载排查",
        scene={},
        kb_id="kb-1",
    )
    assert isinstance(result, RetrievalResult)
    assert result.gate.allowed is True
    assert len(result.citations) == 2
    assert len(result.query_variants) >= 1
    assert result.latency_ms >= 0


def test_pipeline_e2e_gate_refuse():
    mock_searcher = MagicMock()
    mock_searcher.search_knowledge.return_value = [
        {"content": "Unrelated", "score": 0.2},
    ]

    pipeline = RetrievalPipeline(
        knowledge_searcher=mock_searcher,
        gate=ConfidenceGate(threshold=0.6),
    )
    result = pipeline.retrieve(
        workspace_id="ws-1",
        goal="quantum computing",
        scene={},
        kb_id="kb-1",
    )
    assert result.gate.refused is True
    assert result.gate.missing_evidence is not None


def test_pipeline_e2e_no_searcher():
    pipeline = RetrievalPipeline(knowledge_searcher=None)
    result = pipeline.retrieve(
        workspace_id="ws-1",
        goal="CPU high",
        scene={},
        kb_id="kb-1",
    )
    assert result.gate.refused is True
    assert result.items == []
