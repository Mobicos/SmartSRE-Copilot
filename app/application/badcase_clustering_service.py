"""Badcase clustering service — group feedback and generate FAQ candidates."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Protocol


class _FeedbackStore(Protocol):
    def list_badcases(self, *, limit: int = 200) -> list[dict[str, Any]]: ...


class _KnowledgeStore(Protocol):
    def create_knowledge_item(self, **kwargs: Any) -> int: ...
    def find_by_dedup_hash(self, kb_id: str, dedup_hash: str) -> dict[str, Any] | None: ...


class _EmbeddingProvider(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


def _normalize(text: str) -> str:
    return text.lower().strip()


def _simple_hash(text: str) -> str:
    return hashlib.sha256(_normalize(text).encode()).hexdigest()[:16]


class BadcaseClusteringService:
    """Cluster badcase feedback items and generate FAQ candidates.

    Badcase feedback accumulates. When same-type corrections reach ``min_count``,
    they are grouped into a cluster and a draft FAQ candidate is generated,
    awaiting human confirmation::

        clustering = BadcaseClusteringService(feedback_store=repo)
        clusters = clustering.find_cluster_candidates(kb_id="kb-1", min_count=5)
        for cluster in clusters:
            faq = clustering.generate_faq_candidate(cluster)
    """

    def __init__(
        self,
        *,
        feedback_store: _FeedbackStore,
        knowledge_store: _KnowledgeStore | None = None,
        embedding_provider: _EmbeddingProvider | None = None,
    ) -> None:
        self._feedback_store = feedback_store
        self._knowledge_store = knowledge_store
        self._embedder = embedding_provider

    def find_cluster_candidates(
        self,
        *,
        kb_id: str,
        min_count: int = 5,
    ) -> list[dict[str, Any]]:
        """Find groups of feedback items with similar correction text.

        Uses simple hash-based grouping for exact matches.
        For near-matches, embedding-based clustering would be used
        when an embedding_provider is configured.

        Returns list of ``{correction_text, count, feedback_ids, suggested_title}``.
        """
        badcases = self._feedback_store.list_badcases(limit=500)
        if not badcases:
            return []

        # Group by normalized correction hash
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for bc in badcases:
            correction = bc.get("correction", "")
            if not correction:
                continue
            hash_key = _simple_hash(correction)
            groups[hash_key].append(bc)

        clusters: list[dict[str, Any]] = []
        for _hash_key, items in groups.items():
            if len(items) < min_count:
                continue

            # Use the most common correction text as representative
            corrections = [it.get("correction", "") for it in items]
            representative = max(set(corrections), key=corrections.count)
            feedback_ids = [it.get("feedback_id", it.get("id", "")) for it in items]

            clusters.append(
                {
                    "correction_text": representative,
                    "count": len(items),
                    "feedback_ids": feedback_ids,
                    "suggested_title": representative[:100],
                    "kb_id": kb_id,
                }
            )

        return clusters

    def generate_faq_candidate(self, cluster: dict[str, Any]) -> dict[str, Any]:
        """Create a draft FAQ item from a cluster of badcase corrections.

        Returns ``{"id": int, "status": "created"}`` if knowledge_store is available,
        or ``{"status": "pending", "cluster": dict}`` for manual promotion.
        """
        if self._knowledge_store is None:
            return {"status": "pending", "cluster": cluster}

        kb_id = cluster.get("kb_id", "")
        correction = cluster.get("correction_text", "")
        suggested_title = cluster.get("suggested_title", "FAQ from badcase cluster")

        dedup_hash = _simple_hash(correction)
        existing = self._knowledge_store.find_by_dedup_hash(kb_id, dedup_hash)
        if existing:
            return {"status": "dedup_conflict", "existing_item": existing}

        item_id = self._knowledge_store.create_knowledge_item(
            knowledge_base_id=kb_id,
            item_type="faq",
            title=suggested_title,
            content=correction,
            dedup_hash=dedup_hash,
            metadata={
                "source": "badcase_cluster",
                "cluster_count": cluster.get("count", 0),
                "feedback_ids": cluster.get("feedback_ids", []),
            },
        )
        return {"id": item_id, "status": "created"}
