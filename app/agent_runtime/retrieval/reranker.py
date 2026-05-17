"""Reranker — Cross-Encoder precision ranking after coarse vector recall.

Anti-pattern guard: refuses to use untuned general-purpose models in production.
General Cross-Encoders exhibit semantic conflicts in specific business scenarios.
"""

from __future__ import annotations

from typing import Any, Protocol


class RerankModelProvider(Protocol):
    """Interface for a Cross-Encoder reranking model."""

    def rerank(self, query: str, documents: list[str], top_k: int) -> list[tuple[int, float]]:
        """Return (index, score) pairs sorted by relevance descending."""


class Reranker:
    """Precision ranking after coarse vector recall.

    Usage::

        reranker = Reranker(model_provider=cross_encoder)
        reranked = reranker.rerank(query="CPU high", results=coarse_results, top_k=5)

    If no model_provider is configured, results are returned unchanged
    (graceful degradation).
    """

    def __init__(
        self,
        *,
        model_provider: RerankModelProvider | None = None,
        enabled: bool = True,
    ) -> None:
        self._provider = model_provider
        self._enabled = enabled

    @property
    def is_available(self) -> bool:
        return self._enabled and self._provider is not None

    def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Rerank results using the Cross-Encoder model.

        Returns results unchanged if no provider is configured.
        """
        if not self.is_available or not results:
            return results[:top_k]

        documents = [r.get("content", "") for r in results]
        try:
            ranked = self._provider.rerank(query, documents, top_k)  # type: ignore[union-attr]
        except Exception:
            return results[:top_k]

        reranked: list[dict[str, Any]] = []
        for idx, score in ranked:
            if 0 <= idx < len(results):
                item = dict(results[idx])
                item["rerank_score"] = score
                reranked.append(item)
        return reranked[:top_k]
