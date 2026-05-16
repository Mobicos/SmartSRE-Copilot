"""Badcase clustering and FAQ candidate generation for the feedback → knowledge loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _char_bigrams(text: str) -> set[str]:
    """Return the set of character bigrams for *text*."""
    return {text[i : i + 2] for i in range(len(text) - 1)} if len(text) >= 2 else {text}


def _char_bigram_jaccard(a: str, b: str) -> float:
    """Jaccard similarity over character bigrams — language-agnostic, dependency-free."""
    if not a or not b:
        return 0.0
    sa, sb = _char_bigrams(a), _char_bigrams(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


@dataclass(frozen=True)
class ClusterAnalysis:
    """One cluster of similar badcases."""

    cluster_id: int
    representative_correction: str
    feedback_ids: list[str] = field(default_factory=list)
    size: int = 0


@dataclass(frozen=True)
class FAQCandidate:
    """An FAQ draft generated from a cluster of similar badcases."""

    cluster_id: int
    title: str
    corrections: list[str] = field(default_factory=list)
    feedback_ids: list[str] = field(default_factory=list)
    suggested_answer: str = ""


class BadcaseClusterer:
    """Group badcases by correction-text similarity and generate FAQ candidates.

    Uses character-bigram Jaccard similarity — no external embeddings required.
    Upgrade the similarity function to vector-based cosine when embedding
    infrastructure is available (Phase 9).
    """

    def __init__(
        self,
        *,
        similarity_threshold: float = 0.5,
        min_cluster_size: int = 5,
    ) -> None:
        self._similarity_threshold = similarity_threshold
        self._min_cluster_size = min_cluster_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def cluster(self, badcases: list[dict[str, Any]]) -> list[ClusterAnalysis]:
        """Single-linkage greedy clustering on correction text similarity.

        Each badcase dict must contain at least ``feedback_id`` and ``correction``.
        """
        if not badcases:
            return []

        clusters: list[dict[str, Any]] = []  # each: {id, representative, ids, corrections}

        for bc in badcases:
            correction = str(bc.get("correction") or "").strip()
            feedback_id = str(bc.get("feedback_id") or "")
            if not correction or not feedback_id:
                continue

            assigned = False
            for cluster in clusters:
                if _char_bigram_jaccard(correction, cluster["representative"]) >= self._similarity_threshold:
                    cluster["ids"].append(feedback_id)
                    cluster["corrections"].append(correction)
                    assigned = True
                    break

            if not assigned:
                clusters.append(
                    {
                        "id": len(clusters),
                        "representative": correction,
                        "ids": [feedback_id],
                        "corrections": [correction],
                    }
                )

        return [
            ClusterAnalysis(
                cluster_id=c["id"],
                representative_correction=c["representative"],
                feedback_ids=list(c["ids"]),
                size=len(c["ids"]),
            )
            for c in clusters
        ]

    def generate_faq_candidates(
        self, badcases: list[dict[str, Any]]
    ) -> list[FAQCandidate]:
        """Return FAQ candidates for clusters whose size >= min_cluster_size."""
        clusters = self.cluster(badcases)
        candidates: list[FAQCandidate] = []

        for cluster in clusters:
            if cluster.size < self._min_cluster_size:
                continue
            cluster_badcases = [
                bc for bc in badcases if bc.get("feedback_id") in cluster.feedback_ids
            ]
            candidates.append(self._cluster_to_faq(cluster, cluster_badcases))

        return candidates

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cluster_to_faq(
        self,
        cluster: ClusterAnalysis,
        badcases: list[dict[str, Any]],
    ) -> FAQCandidate:
        unique_corrections = list(dict.fromkeys(
            str(bc.get("correction") or "").strip()
            for bc in badcases
            if bc.get("correction")
        ))
        goals = [
            _goal_from_badcase(bc)
            for bc in badcases
            if _goal_from_badcase(bc)
        ]
        title = _most_common(goals) if goals else "Unknown FAQ topic"
        suggested_answer = _deduplicated_summary(unique_corrections)

        return FAQCandidate(
            cluster_id=cluster.cluster_id,
            title=title,
            corrections=unique_corrections,
            feedback_ids=list(cluster.feedback_ids),
            suggested_answer=suggested_answer,
        )


def _goal_from_badcase(bc: dict[str, Any]) -> str:
    run = bc.get("run")
    if isinstance(run, dict):
        goal = run.get("goal")
        if goal:
            return str(goal)
    return ""


def _most_common(items: list[str]) -> str:
    if not items:
        return ""
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return max(counts, key=lambda k: counts[k])


def _deduplicated_summary(corrections: list[str]) -> str:
    seen: list[str] = []
    for c in corrections:
        if c not in seen:
            seen.append(c)
    return "\n---\n".join(seen) if seen else ""
