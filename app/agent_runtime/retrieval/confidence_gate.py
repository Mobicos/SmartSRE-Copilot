"""Confidence gate — enforce minimum quality threshold on retrieval results."""

from __future__ import annotations

from app.agent_runtime.knowledge_types import GateResult

DEFAULT_THRESHOLD = 0.6


class ConfidenceGate:
    """Evaluate retrieval results against a confidence threshold.

    If the best score is below the threshold, results are refused and a
    "missing evidence" message is generated::

        gate = ConfidenceGate()
        result = gate.evaluate(results, threshold=0.6)
        if result.refused:
            # inject "missing evidence + suggested next step" into context
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self._threshold = threshold

    def evaluate(
        self,
        results: list[dict],
        threshold: float | None = None,
    ) -> GateResult:
        """Evaluate results against the confidence threshold."""
        effective_threshold = threshold if threshold is not None else self._threshold

        if not results:
            return GateResult(
                allowed=False,
                results=[],
                refused=True,
                best_score=0.0,
                missing_evidence="未检索到相关知识，请基于当前证据进行分析。",
            )

        best_score = max(r.get("score", 0.0) for r in results)

        if best_score < effective_threshold:
            return GateResult(
                allowed=False,
                results=[],
                refused=True,
                best_score=best_score,
                missing_evidence=(
                    f"检索置信度不足 ({best_score:.2f} < {effective_threshold:.2f})。"
                    "建议：基于当前证据继续诊断，或尝试更具体的查询词。"
                ),
            )

        return GateResult(
            allowed=True,
            results=results,
            refused=False,
            best_score=best_score,
        )
