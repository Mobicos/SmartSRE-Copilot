"""Semantic cache — cache high-confidence FAQ/SOP answers for repeated queries."""

from __future__ import annotations

import time
from typing import Any, Protocol

from app.agent_runtime.knowledge_types import CacheResult

_DEFAULT_SIMILARITY_THRESHOLD = 0.95
_DEFAULT_TTL_SECONDS = 3600


class _CacheVectorSearch(Protocol):
    def search_similar_documents(self, query: str, top_k: int = 3) -> list[Any]: ...


class SemanticCache:
    """In-memory semantic cache for retrieval results.

    High-confidence FAQ/SOP queries that repeat can return cached answers
    directly, reducing latency and token cost::

        cache = SemanticCache(vector_search=vector_search_service)
        hit = cache.lookup(workspace_id="ws-1", query="CPU high steps")
        if hit and hit.cached:
            return hit.result
    """

    def __init__(
        self,
        *,
        vector_search: _CacheVectorSearch | None = None,
        similarity_threshold: float = _DEFAULT_SIMILARITY_THRESHOLD,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self._vector_search = vector_search
        self._threshold = similarity_threshold
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, dict[str, Any], list[str]]] = {}

    def lookup(
        self,
        *,
        workspace_id: str,
        query: str,
    ) -> CacheResult | None:
        """Look up cached result for a query.

        Returns CacheResult(cached=True, ...) on hit, None on miss.
        """
        cache_key = f"{workspace_id}::{query.lower().strip()}"
        entry = self._cache.get(cache_key)

        if entry is not None:
            ts, result, item_ids = entry
            if time.time() - ts < self._ttl:
                return CacheResult(cached=True, result=result, hit_item_ids=item_ids)
            del self._cache[cache_key]

        # Try semantic similarity lookup
        if self._vector_search is not None:
            try:
                results = self._vector_search.search_similar_documents(query, top_k=1)
                if results and results[0].score >= self._threshold:  # type: ignore[union-attr]
                    result_data = {
                        "content": results[0].content,  # type: ignore[union-attr]
                        "score": results[0].score,  # type: ignore[union-attr]
                    }
                    self._cache[cache_key] = (time.time(), result_data, [])
                    return CacheResult(
                        cached=True,
                        result=result_data,
                        hit_item_ids=[],
                    )
            except Exception:
                pass

        return None

    def store(
        self,
        *,
        workspace_id: str,
        query: str,
        result: dict[str, Any],
        item_ids: list[str] | None = None,
    ) -> None:
        """Cache a retrieval result for future lookups."""
        cache_key = f"{workspace_id}::{query.lower().strip()}"
        self._cache[cache_key] = (time.time(), result, item_ids or [])

    def clear(self) -> None:
        self._cache.clear()
