"""Unit tests for KnowledgeService (knowledge CRUD + dedup)."""

from __future__ import annotations

from typing import Any

from app.application.knowledge_service import KnowledgeService, _compute_dedup_hash


class _FakeKnowledgeRepo:
    def __init__(self) -> None:
        self._items: dict[int, dict[str, Any]] = {}
        self._next_id = 1
        self._audit_log: list[dict[str, Any]] = []
        self._dedup_store: dict[str, dict[str, Any]] = {}

    def create(self, **kwargs: Any) -> int:
        item_id = self._next_id
        self._next_id += 1
        self._items[item_id] = {"id": item_id, **kwargs, "status": "draft"}
        self._dedup_store[kwargs.get("dedup_hash", "")] = self._items[item_id]
        return item_id

    def get(self, item_id: int) -> dict[str, Any] | None:
        return self._items.get(item_id)

    def list_by_type(
        self, kb_id: str, item_type: str, *, status: str = "published"
    ) -> list[dict[str, Any]]:
        return [
            v
            for v in self._items.values()
            if v.get("knowledge_base_id") == kb_id
            and v.get("item_type") == item_type
            and v.get("status") == status
        ]

    def list_drafts(self, kb_id: str) -> list[dict[str, Any]]:
        return [
            v
            for v in self._items.values()
            if v.get("knowledge_base_id") == kb_id and v.get("status") == "draft"
        ]

    def update_status(
        self, item_id: int, status: str, *, published_by: str | None = None
    ) -> None:
        if item_id in self._items:
            self._items[item_id]["status"] = status

    def find_by_dedup_hash(self, kb_id: str, dedup_hash: str) -> dict[str, Any] | None:
        return self._dedup_store.get(dedup_hash)

    def count_by_type(self, knowledge_base_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for v in self._items.values():
            if (
                v.get("knowledge_base_id") == knowledge_base_id
                and v.get("status") == "published"
            ):
                t = v.get("item_type", "unknown")
                counts[t] = counts.get(t, 0) + 1
        return counts

    def log_audit(self, **kwargs: Any) -> None:
        self._audit_log.append(kwargs)


def _make_service() -> tuple[KnowledgeService, _FakeKnowledgeRepo]:
    repo = _FakeKnowledgeRepo()
    service = KnowledgeService(item_repository=repo)
    return service, repo


# ---------------------------------------------------------------------------
# create_item
# ---------------------------------------------------------------------------


def test_create_item_success():
    service, repo = _make_service()
    result = service.create_item(
        kb_id="kb-1",
        item_type="faq",
        title="CPU high steps",
        content="Check load average first",
    )
    assert result["status"] == "created"
    assert result["id"] == 1
    assert len(repo._audit_log) == 1
    assert repo._audit_log[0]["action"] == "created"


def test_create_item_dedup_conflict():
    service, repo = _make_service()
    service.create_item(
        kb_id="kb-1",
        item_type="faq",
        title="First",
        content="Same content",
    )
    result = service.create_item(
        kb_id="kb-1",
        item_type="faq",
        title="Second",
        content="Same content",
    )
    assert result["status"] == "dedup_conflict"
    assert "existing_item" in result


def test_create_item_different_content_no_conflict():
    service, _ = _make_service()
    r1 = service.create_item(kb_id="kb-1", item_type="faq", title="A", content="Content A")
    r2 = service.create_item(kb_id="kb-1", item_type="faq", title="B", content="Content B")
    assert r1["status"] == "created"
    assert r2["status"] == "created"


# ---------------------------------------------------------------------------
# publish / reject
# ---------------------------------------------------------------------------


def test_publish_item():
    service, repo = _make_service()
    result = service.create_item(kb_id="kb-1", item_type="faq", title="T", content="C")
    service.publish_item(result["id"], published_by="admin")
    assert repo._items[result["id"]]["status"] == "published"


def test_reject_item():
    service, repo = _make_service()
    result = service.create_item(kb_id="kb-1", item_type="faq", title="T", content="C")
    service.reject_item(result["id"], actor="admin")
    assert repo._items[result["id"]]["status"] == "archived"


# ---------------------------------------------------------------------------
# type distribution
# ---------------------------------------------------------------------------


def test_get_type_distribution():
    service, repo = _make_service()
    service.create_item(kb_id="kb-1", item_type="faq", title="A", content="a")
    service.create_item(kb_id="kb-1", item_type="faq", title="B", content="b")
    service.create_item(kb_id="kb-1", item_type="sop", title="C", content="c")
    # Publish all
    for item_id in list(repo._items.keys()):
        service.publish_item(item_id, published_by="admin")
    dist = service.get_type_distribution("kb-1")
    assert dist["faq"] == 2
    assert dist["sop"] == 1


# ---------------------------------------------------------------------------
# dedup hash
# ---------------------------------------------------------------------------


def test_dedup_hash_normalizes_whitespace():
    h1 = _compute_dedup_hash("  hello   world  ")
    h2 = _compute_dedup_hash("hello world")
    assert h1 == h2


def test_dedup_hash_case_insensitive():
    h1 = _compute_dedup_hash("CPU High")
    h2 = _compute_dedup_hash("cpu high")
    assert h1 == h2


# ---------------------------------------------------------------------------
# list_drafts
# ---------------------------------------------------------------------------


def test_list_drafts():
    service, _ = _make_service()
    service.create_item(kb_id="kb-1", item_type="faq", title="Draft", content="D")
    r = service.create_item(kb_id="kb-1", item_type="faq", title="Pub", content="P")
    service.publish_item(r["id"], published_by="admin")
    drafts = service.list_drafts("kb-1")
    assert len(drafts) == 1
    assert drafts[0]["title"] == "Draft"
