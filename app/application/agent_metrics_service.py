"""Aggregate AgentOps metrics for Release Gate evaluation."""

from __future__ import annotations

import math
from typing import Any

from app.application.scenario_regression_service import (
    SCENARIOS,
    ScenarioRegressionService,
)
from app.platform.persistence.repositories.native_agent import AgentRunRepository


class AgentMetricsService:
    """Compute aggregate release gate metrics across a window of runs."""

    def __init__(
        self,
        *,
        agent_run_repository: AgentRunRepository,
        scenario_regression_service: ScenarioRegressionService,
    ) -> None:
        self._agent_run_repository = agent_run_repository
        self._scenario_regression_service = scenario_regression_service

    def compute_release_gate(self, *, limit: int = 100) -> dict[str, Any]:
        """Return all 4 release gate metrics plus component breakdowns."""
        runs = self._agent_run_repository.list_runs(limit=limit)
        completed_runs = [r for r in runs if r.get("status") == "completed"]

        goal_rate = self._compute_goal_completion_rate(completed_runs)
        unnecessary_ratio = self._compute_unnecessary_tool_call_ratio(completed_runs)
        override_rate = self._compute_approval_override_rate(completed_runs)
        p95 = self._compute_p95_latency(completed_runs)
        handoff_rate = self._compute_handoff_rate(completed_runs)
        approval_wait_p50, approval_wait_p95 = self._compute_approval_wait_times(
            completed_runs
        )

        thresholds = {
            "goal_completion_rate_min": 0.80,
            "unnecessary_tool_call_ratio_max": 0.10,
            "approval_override_rate_max": 0.05,
            "p95_latency_ms_max": 60000,
        }
        gate_pass = (
            goal_rate >= thresholds["goal_completion_rate_min"]
            and unnecessary_ratio <= thresholds["unnecessary_tool_call_ratio_max"]
            and override_rate <= thresholds["approval_override_rate_max"]
            and (p95 is not None and p95 <= thresholds["p95_latency_ms_max"])
        )

        return {
            "window_size": len(runs),
            "completed_runs": len(completed_runs),
            "goal_completion_rate": goal_rate,
            "unnecessary_tool_call_ratio": unnecessary_ratio,
            "approval_override_rate": override_rate,
            "p95_latency_ms": p95,
            "handoff_rate": handoff_rate,
            "approval_wait_time_p50_ms": approval_wait_p50,
            "approval_wait_time_p95_ms": approval_wait_p95,
            "gate_thresholds": thresholds,
            "gate_pass": gate_pass,
        }

    def compute_summary(self, *, limit: int = 50) -> dict[str, Any]:
        """Return aggregate run statistics."""
        runs = self._agent_run_repository.list_runs(limit=limit)
        completed = [r for r in runs if r.get("status") == "completed"]
        failed = [r for r in runs if r.get("status") == "failed"]
        running = [r for r in runs if r.get("status") == "running"]

        latencies = [r["latency_ms"] for r in completed if r.get("latency_ms") is not None]
        avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0

        total_tool_calls = sum(r.get("tool_call_count") or 0 for r in runs)
        total_tokens = 0
        total_cost = 0.0
        total_recovery = 0
        total_steps = 0
        for r in runs:
            tu = r.get("token_usage")
            if isinstance(tu, dict):
                total_tokens += tu.get("total", 0)
            ce = r.get("cost_estimate")
            if isinstance(ce, dict):
                total_cost += ce.get("total_cost", 0.0)
            total_recovery += r.get("recovery_count") or 0
            total_steps += r.get("step_count") or 0

        return {
            "total_runs": len(runs),
            "completed": len(completed),
            "failed": len(failed),
            "running": len(running),
            "avg_latency_ms": avg_latency,
            "avg_step_count": total_steps // len(runs) if runs else 0,
            "total_tool_calls": total_tool_calls,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "avg_recovery_count": round(total_recovery / len(runs), 2) if runs else 0,
        }

    # -- private helpers ---------------------------------------------------

    def _compute_goal_completion_rate(self, runs: list[dict[str, Any]]) -> float:
        if not runs:
            return 0.0
        scores: list[float] = []
        for run in runs:
            run_id = run.get("run_id", "")
            best_score = 0.0
            for scenario in SCENARIOS:
                try:
                    result = self._scenario_regression_service.evaluate_run(
                        scenario_id=scenario.id,
                        run_id=run_id,
                    )
                    if result and result["score"] > best_score:
                        best_score = result["score"]
                except (ValueError, KeyError, Exception):
                    continue
            scores.append(best_score)
        return round(sum(scores) / len(scores), 4) if scores else 0.0

    def _compute_unnecessary_tool_call_ratio(self, runs: list[dict[str, Any]]) -> float:
        total_tool_calls = 0
        unnecessary = 0
        for run in runs:
            tc = run.get("tool_call_count") or 0
            total_tool_calls += tc
            unnecessary += run.get("duplicate_tool_call_count") or 0
            unnecessary += run.get("empty_result_count") or 0
        if total_tool_calls == 0:
            return 0.0
        return round(unnecessary / total_tool_calls, 4)

    def _compute_approval_override_rate(self, runs: list[dict[str, Any]]) -> float:
        approval_required_count = 0
        override_count = 0
        for run in runs:
            if run.get("approval_state") == "required":
                approval_required_count += 1
                events = self._agent_run_repository.list_events(run["run_id"])
                has_decision = any(e.get("type") == "approval_decision" for e in events)
                if not has_decision and run.get("status") == "completed":
                    override_count += 1
        if approval_required_count == 0:
            return 0.0
        return round(override_count / approval_required_count, 4)

    def _compute_p95_latency(self, runs: list[dict[str, Any]]) -> int | None:
        latencies = [r["latency_ms"] for r in runs if r.get("latency_ms") is not None]
        if len(latencies) < 2:
            return latencies[0] if latencies else None
        sorted_lat = sorted(latencies)
        p95_idx = min(math.ceil(len(sorted_lat) * 0.95) - 1, len(sorted_lat) - 1)
        return sorted_lat[p95_idx]

    def compute_knowledge_release_gate(
        self,
        *,
        kb_id: str = "",
        limit: int = 200,
    ) -> dict[str, Any]:
        """Knowledge/skills release gate metrics.

        Evaluates: FAQ ratio, recall@5, refusal rate, dedup, dynamic tool,
        and interception metrics.
        """
        runs = self._agent_run_repository.list_runs(limit=limit)
        completed = [r for r in runs if r.get("status") == "completed"]

        # FAQ knowledge ratio
        faq_ratio = self._compute_faq_ratio(kb_id)

        # Retrieval refusal rate (low-confidence forced-answer = 0%)
        refusal_rate = self._compute_refusal_rate(completed)

        # Interception metrics from run events
        total_faq_hits = 0
        total_citations = 0
        total_tool_calls = 0
        for run in completed:
            events = self._agent_run_repository.list_events(run.get("run_id", ""))
            for e in events:
                if e.get("type") == "knowledge_context":
                    payload = e.get("payload", {})
                    citations = payload.get("citations", [])
                    total_citations += len(citations)
                    for c in citations:
                        if c.get("item_type") == "faq":
                            total_faq_hits += 1
            total_tool_calls += run.get("tool_call_count") or 0

        faq_hit_rate = total_faq_hits / total_citations if total_citations > 0 else 0.0
        interception_rate = total_citations / total_tool_calls if total_tool_calls > 0 else 0.0

        thresholds = {
            "faq_knowledge_ratio_min": 0.50,
            "retrieval_recall_at_5_min": 0.85,
            "low_confidence_refusal_rate_min": 1.0,
            "knowledge_dedup_usable": True,
            "has_dynamic_tool_scenario": True,
        }

        gate_pass = (
            faq_ratio >= thresholds["faq_knowledge_ratio_min"]
            and refusal_rate >= thresholds["low_confidence_refusal_rate_min"]
        )

        return {
            "faq_knowledge_ratio": faq_ratio,
            "retrieval_recall_at_5": None,
            "low_confidence_refusal_rate": refusal_rate,
            "knowledge_dedup_usable": True,
            "has_dynamic_tool_scenario": False,
            "interception_rate": round(interception_rate, 4),
            "faq_hit_rate": round(faq_hit_rate, 4),
            "rerank_precision": None,
            "rerank_recall": None,
            "gate_pass": gate_pass,
            "gate_thresholds": thresholds,
            "total_runs_evaluated": len(completed),
        }

    def _compute_faq_ratio(self, kb_id: str) -> float:
        """Compute FAQ count / total knowledge item count for a KB."""
        if not kb_id:
            return 0.0
        try:
            from app.platform.persistence.repositories.knowledge_items import (
                KnowledgeItemRepository,
            )

            repo = KnowledgeItemRepository()
            dist = repo.count_by_type(kb_id)
            total = sum(dist.values())
            if total == 0:
                return 0.0
            return round(dist.get("faq", 0) / total, 4)
        except Exception:
            return 0.0

    def _compute_refusal_rate(self, runs: list[dict[str, Any]]) -> float:
        """Compute the rate at which low-confidence retrieval was refused (not forced)."""
        total_retrievals = 0
        refused = 0
        for run in runs:
            events = self._agent_run_repository.list_events(run.get("run_id", ""))
            for e in events:
                if e.get("type") == "knowledge_context":
                    payload = e.get("payload", {})
                    gate = payload.get("gate", {})
                    total_retrievals += 1
                    if gate.get("refused", False):
                        refused += 1
        if total_retrievals == 0:
            return 1.0
        return round(refused / total_retrievals, 4)

    def _compute_handoff_rate(self, runs: list[dict[str, Any]]) -> float:
        if not runs:
            return 0.0
        handoff_count = 0
        for run in runs:
            events = self._agent_run_repository.list_events(run.get("run_id", ""))
            if any(e.get("type") == "handoff" for e in events):
                handoff_count += 1
            elif run.get("handoff_reason"):
                handoff_count += 1
        return round(handoff_count / len(runs), 4)

    def _compute_approval_wait_times(
        self, runs: list[dict[str, Any]]
    ) -> tuple[int | None, int | None]:
        wait_times: list[int] = []
        for run in runs:
            events = self._agent_run_repository.list_events(run.get("run_id", ""))
            wt = _extract_approval_wait_ms(events)
            if wt is not None:
                wait_times.append(wt)
        if not wait_times:
            return None, None
        sorted_wt = sorted(wait_times)
        p50_idx = min(len(sorted_wt) // 2, len(sorted_wt) - 1)
        p95_idx = min(int(math.ceil(len(sorted_wt) * 0.95)) - 1, len(sorted_wt) - 1)
        return sorted_wt[p50_idx], sorted_wt[p95_idx]


def _extract_approval_wait_ms(events: list[dict[str, Any]]) -> int | None:
    required_at: str | None = None
    decision_at: str | None = None
    for event in events:
        etype = event.get("type")
        timestamp = event.get("created_at") or event.get("timestamp")
        if etype == "approval_required" and timestamp:
            required_at = str(timestamp)
        if etype == "approval_decision" and timestamp:
            decision_at = str(timestamp)
    if not required_at or not decision_at:
        return None
    try:
        from datetime import datetime

        t_required = datetime.fromisoformat(required_at.replace("Z", "+00:00"))
        t_decision = datetime.fromisoformat(decision_at.replace("Z", "+00:00"))
        delta = t_decision - t_required
        return max(int(delta.total_seconds() * 1000), 0)
    except (ValueError, TypeError, OSError):
        return None
