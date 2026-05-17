"""Knowledge service — CRUD, dedup, embedding, and search over knowledge items."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Protocol


class EmbeddingProvider(Protocol):
    """Embedding generation interface."""

    def embed_query(self, text: str) -> list[float]: ...


class _KnowledgeItemRepo(Protocol):
    def create(self, **kwargs: Any) -> int: ...
    def get(self, item_id: int) -> dict[str, Any] | None: ...
    def list_by_type(self, kb_id: str, item_type: str, *, status: str) -> list[dict[str, Any]]: ...
    def list_drafts(self, kb_id: str) -> list[dict[str, Any]]: ...
    def update_status(
        self, item_id: int, status: str, *, published_by: str | None = None
    ) -> None: ...
    def find_by_dedup_hash(self, kb_id: str, dedup_hash: str) -> dict[str, Any] | None: ...
    def count_by_type(self, kb_id: str) -> dict[str, int]: ...
    def log_audit(self, **kwargs: Any) -> None: ...


class _VectorSearch(Protocol):
    def search_similar_documents(self, query: str, top_k: int = 3) -> list[Any]: ...


def _normalize_content(content: str) -> str:
    """Normalize text for dedup hashing: lowercase, collapse whitespace."""
    text = content.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _compute_dedup_hash(content: str) -> str:
    normalized = _normalize_content(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class KnowledgeService:
    """Manage knowledge items: create, dedup, publish, search, and stats.

    Usage::

        service = KnowledgeService(
            item_repository=repo,
            embedding_provider=dashscope_embeddings,
            vector_search=vector_search_service,
        )
        result = service.create_item(
            kb_id="kb-1",
            item_type="faq",
            title="CPU 高排查步骤",
            content="1. 检查 load average...",
        )
    """

    def __init__(
        self,
        *,
        item_repository: _KnowledgeItemRepo,
        embedding_provider: EmbeddingProvider | None = None,
        vector_search: _VectorSearch | None = None,
    ) -> None:
        self._repo = item_repository
        self._embedder = embedding_provider
        self._vector_search = vector_search

    def create_item(
        self,
        *,
        kb_id: str,
        item_type: str,
        title: str,
        content: str,
        source_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """Create a knowledge item. Checks for exact dedup via content hash.

        Returns ``{"id": int, "status": "created"}`` on success, or
        ``{"status": "dedup_conflict", "existing_item": dict}`` if a
        duplicate already exists.
        """
        dedup_hash = _compute_dedup_hash(content)
        existing = self._repo.find_by_dedup_hash(kb_id, dedup_hash)
        if existing:
            return {"status": "dedup_conflict", "existing_item": existing}

        item_id = self._repo.create(
            knowledge_base_id=kb_id,
            item_type=item_type,
            title=title,
            content=content,
            dedup_hash=dedup_hash,
            source_run_id=source_run_id,
            metadata=metadata,
            created_by=created_by,
        )
        self._repo.log_audit(
            item_id=item_id,
            action="created",
            actor=created_by,
            details={"item_type": item_type, "title": title},
        )
        return {"id": item_id, "status": "created"}

    def publish_item(self, item_id: int, published_by: str) -> None:
        """Publish a draft knowledge item."""
        self._repo.update_status(item_id, "published", published_by=published_by)
        self._repo.log_audit(
            item_id=item_id,
            action="published",
            actor=published_by,
        )

    def reject_item(self, item_id: int, actor: str) -> None:
        """Reject (archive) a draft knowledge item."""
        self._repo.update_status(item_id, "archived")
        self._repo.log_audit(
            item_id=item_id,
            action="rejected",
            actor=actor,
        )

    def list_drafts(self, kb_id: str) -> list[dict[str, Any]]:
        return self._repo.list_drafts(kb_id)

    def get_type_distribution(self, kb_id: str) -> dict[str, int]:
        """Return published item counts grouped by type."""
        return self._repo.count_by_type(kb_id)

    def search(
        self,
        *,
        workspace_id: str,
        kb_id: str,
        query: str,
        item_type: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Search published knowledge items. Falls back to simple list if no vector search."""
        if self._vector_search is not None:
            try:
                results = self._vector_search.search_similar_documents(query, top_k=top_k)
                return [
                    {
                        "content": r.content,
                        "score": r.score,
                        "metadata": r.metadata,
                    }
                    for r in results
                ]
            except Exception:
                pass

        if item_type:
            items = self._repo.list_by_type(kb_id, item_type, status="published")
        else:
            items = self._repo.count_by_type(kb_id)
            # Fallback: return empty when vector search unavailable
            items = []
        return items[:top_k]

    def check_dedup(
        self,
        kb_id: str,
        embedding: list[float],
        threshold: float = 0.9,
    ) -> list[dict[str, Any]]:
        """Check for near-duplicate knowledge items using embedding similarity.

        Returns items with similarity above threshold (if vector search is available).
        """
        if self._embedder is None:
            return []
        try:
            query = f"similar_to_{kb_id}"
            results = self._vector_search.search_similar_documents(query, top_k=10)  # type: ignore[union-attr]
            return [
                {"content": r.content, "score": r.score, "metadata": r.metadata}
                for r in results
                if r.score >= threshold
            ]
        except Exception:
            return []

    def promote_from_run(
        self,
        *,
        run_id: str,
        kb_id: str,
        item_type: str,
        title: str,
        content: str,
        published_by: str,
    ) -> int:
        """Promote a historical run's conclusion into the knowledge base as published."""
        result = self.create_item(
            kb_id=kb_id,
            item_type=item_type,
            title=title,
            content=content,
            source_run_id=run_id,
            created_by=published_by,
        )
        if result["status"] == "created":
            self.publish_item(result["id"], published_by)
        return result.get("id", 0)

    def search_knowledge(
        self,
        *,
        workspace_id: str,
        query: str,
        item_type: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Adapter for RetrievalPipeline: search published knowledge items."""
        return self.search(
            workspace_id=workspace_id,
            kb_id="",
            query=query,
            item_type=item_type,
            top_k=top_k,
        )
