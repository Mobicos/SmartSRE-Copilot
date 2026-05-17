"""Unit tests for BadcaseClusteringService (knowledge learning loop)."""

from __future__ import annotations

from typing import Any

from app.application.badcase_clustering_service import BadcaseClusteringService


class _FakeFeedbackStore:
    def __init__(self, badcases: list[dict[str, Any]]) -> None:
        self._badcases = badcases

    def list_badcases(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return self._badcases[:limit]


class _FakeKnowledgeStore:
    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []
        self._next_id = 1

    def create_knowledge_item(self, **kwargs: Any) -> int:
        item_id = self._next_id
        self._next_id += 1
        self._items.append({"id": item_id, **kwargs})
        return item_id

    def find_by_dedup_hash(self, kb_id: str, dedup_hash: str) -> dict[str, Any] | None:
        for item in self._items:
            if item.get("dedup_hash") == dedup_hash:
                return item
        return None


def _make_service(
    badcases: list[dict[str, Any]],
    knowledge_store: _FakeKnowledgeStore | None = None,
) -> BadcaseClusteringService:
    return BadcaseClusteringService(
        feedback_store=_FakeFeedbackStore(badcases),  # type: ignore[arg-type]
        knowledge_store=knowledge_store,  # type: ignore[arg-type]
    )


def test_cluster_discovery():
    badcases = [
        {"feedback_id": f"fb-{i}", "correction": "检查连接池配置", "badcase_flag": True}
        for i in range(6)
    ]
    service = _make_service(badcases)
    clusters = service.find_cluster_candidates(kb_id="kb-1", min_count=5)
    assert len(clusters) == 1
    assert clusters[0]["count"] == 6
    assert clusters[0]["correction_text"] == "检查连接池配置"


def test_cluster_below_min_count():
    badcases = [
        {"feedback_id": f"fb-{i}", "correction": "检查连接池配置", "badcase_flag": True}
        for i in range(3)
    ]
    service = _make_service(badcases)
    clusters = service.find_cluster_candidates(kb_id="kb-1", min_count=5)
    assert len(clusters) == 0


def test_faq_generation_with_knowledge_store():
    kb_store = _FakeKnowledgeStore()
    service = _make_service(
        badcases=[
            {"feedback_id": "fb-1", "correction": "重启服务"},
            {"feedback_id": "fb-2", "correction": "重启服务"},
            {"feedback_id": "fb-3", "correction": "重启服务"},
            {"feedback_id": "fb-4", "correction": "重启服务"},
            {"feedback_id": "fb-5", "correction": "重启服务"},
        ],
        knowledge_store=kb_store,
    )
    clusters = service.find_cluster_candidates(kb_id="kb-1", min_count=5)
    assert len(clusters) == 1
    result = service.generate_faq_candidate(clusters[0])
    assert result["status"] == "created"
    assert len(kb_store._items) == 1
    assert kb_store._items[0]["item_type"] == "faq"


def test_faq_generation_without_knowledge_store():
    service = _make_service(badcases=[], knowledge_store=None)
    result = service.generate_faq_candidate(
        {"correction_text": "test", "count": 5, "kb_id": "kb-1"}
    )
    assert result["status"] == "pending"


def test_faq_generation_dedup_conflict():
    kb_store = _FakeKnowledgeStore()
    kb_store._items.append({"id": 99, "dedup_hash": "existing_hash", "title": "existing"})
    service = _make_service(badcases=[], knowledge_store=kb_store)

    # Patch _simple_hash to return the known hash
    import app.application.badcase_clustering_service as mod

    original_hash = mod._simple_hash
    mod._simple_hash = lambda text: "existing_hash"  # type: ignore[assignment]
    try:
        result = service.generate_faq_candidate(
            {"correction_text": "test", "count": 5, "kb_id": "kb-1"}
        )
        assert result["status"] == "dedup_conflict"
    finally:
        mod._simple_hash = original_hash  # type: ignore[assignment]


def test_empty_badcases():
    service = _make_service(badcases=[])
    clusters = service.find_cluster_candidates(kb_id="kb-1", min_count=5)
    assert clusters == []


def test_multiple_clusters():
    badcases = [
        {"feedback_id": "fb-1", "correction": "检查CPU"},
        {"feedback_id": "fb-2", "correction": "检查CPU"},
        {"feedback_id": "fb-3", "correction": "检查CPU"},
        {"feedback_id": "fb-4", "correction": "检查CPU"},
        {"feedback_id": "fb-5", "correction": "检查CPU"},
        {"feedback_id": "fb-6", "correction": "重启服务"},
        {"feedback_id": "fb-7", "correction": "重启服务"},
        {"feedback_id": "fb-8", "correction": "重启服务"},
        {"feedback_id": "fb-9", "correction": "重启服务"},
        {"feedback_id": "fb-10", "correction": "重启服务"},
    ]
    service = _make_service(badcases)
    clusters = service.find_cluster_candidates(kb_id="kb-1", min_count=5)
    assert len(clusters) == 2
    texts = {c["correction_text"] for c in clusters}
    assert "检查CPU" in texts
    assert "重启服务" in texts
