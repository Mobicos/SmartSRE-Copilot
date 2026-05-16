"""Collaborative intervention primitives for the agent loop.

InterventionBridge stores pending interventions per run and applies them
during the loop's observe→decide cycle.  The loop calls ``pending()``
before each step and ``apply_injected_evidence()`` / ``apply_replace_decision()``
at the right point in the cycle.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.agent_runtime.decision import (
    AgentDecision,
    AgentDecisionState,
    AgentGoalContract,
    AgentObservation,
    EvidenceAssessment,
)


class InterventionType(str, Enum):
    INJECT_EVIDENCE = "inject_evidence"
    REPLACE_TOOL_CALL = "replace_tool_call"
    MODIFY_GOAL = "modify_goal"


@dataclass
class Intervention:
    """A single human intervention queued for a running agent."""

    intervention_id: str
    run_id: str
    intervention_type: InterventionType
    payload: dict[str, Any] = field(default_factory=dict)
    applied: bool = False


class InterventionBridge:
    """Thread-safe queue of pending interventions per run.

    Usage::

        bridge = InterventionBridge()
        bridge.add(Intervention(
            intervention_id="int-1",
            run_id="run-1",
            intervention_type=InterventionType.INJECT_EVIDENCE,
            payload={"source": "human", "content": "检查数据库连接池"},
        ))

        # Inside loop, before decide step:
        interventions = bridge.pending("run-1")
        for iv in interventions:
            state = bridge.apply_injected_evidence(iv, state)
            bridge.mark_applied(iv)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, list[Intervention]] = defaultdict(list)

    def add(self, intervention: Intervention) -> None:
        """Queue an intervention for a run."""
        with self._lock:
            self._queues[intervention.run_id].append(intervention)

    def pending(self, run_id: str) -> list[Intervention]:
        """Return un-applied interventions for *run_id* (snapshot)."""
        with self._lock:
            return [iv for iv in self._queues.get(run_id, []) if not iv.applied]

    def mark_applied(self, intervention: Intervention) -> None:
        """Mark an intervention as applied so it is not re-processed."""
        with self._lock:
            intervention.applied = True

    def clear(self, run_id: str) -> None:
        """Remove all interventions for a run (used on run completion)."""
        with self._lock:
            self._queues.pop(run_id, None)

    # -- apply helpers -------------------------------------------------------

    @staticmethod
    def apply_injected_evidence(
        intervention: Intervention,
        state: AgentDecisionState,
    ) -> AgentDecisionState:
        """Append human-provided evidence to the decision state."""
        content = intervention.payload.get("content", "")
        source = intervention.payload.get("source", "human_intervention")
        observation = AgentObservation(
            source=source,
            summary=content,
            confidence=float(intervention.payload.get("confidence", 1.0)),
        )
        observations = list(state.observations)
        observations.append(observation)
        return state.model_copy(update={"observations": observations})

    @staticmethod
    def apply_replace_decision(
        intervention: Intervention,
        decision: AgentDecision,
    ) -> AgentDecision:
        """Override a decision with human-specified tool call parameters."""
        payload = intervention.payload
        updates: dict[str, Any] = {}
        if "selected_tool" in payload:
            updates["selected_tool"] = payload["selected_tool"]
        if "tool_arguments" in payload:
            updates["tool_arguments"] = payload["tool_arguments"]
        if "reasoning_summary" in payload:
            updates["reasoning_summary"] = payload["reasoning_summary"]
        if not updates:
            return decision
        return decision.model_copy(update=updates)

    @staticmethod
    def apply_modify_goal(
        intervention: Intervention,
        state: AgentDecisionState,
    ) -> AgentDecisionState:
        """Update the run goal with human-specified modifications."""
        payload = intervention.payload
        current = state.goal
        updates: dict[str, Any] = {}
        if "goal" in payload:
            updates["goal"] = payload["goal"]
        if "success_criteria" in payload:
            updates["success_criteria"] = payload["success_criteria"]
        if "priority" in payload:
            updates["priority"] = payload["priority"]
        if not updates:
            return state
        new_goal = current.model_copy(update=updates)
        return state.model_copy(update={"goal": new_goal})
