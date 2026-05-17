"""JSON fixture schema for deterministic replay evaluation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class ExpectedToolCall(BaseModel):
    """Expected tool invocation in a fixture replay."""

    tool_name: str
    arguments_subset: dict[str, Any] = Field(default_factory=dict)
    index: int | None = None


class ExpectedEvent(BaseModel):
    """Expected event emitted during a fixture replay."""

    type: str
    payload_subset: dict[str, Any] = Field(default_factory=dict)


class ReplayFixture(BaseModel):
    """Deterministic fixture describing expected replay behaviour."""

    fixture_id: str
    scenario_id: str
    title: str
    goal: str
    terminal_status: str = "completed"
    required_event_types: tuple[str, ...] = ()
    expected_tool_calls: list[ExpectedToolCall] = Field(default_factory=list)
    expected_signals: tuple[str, ...] = ()
    blocked_terms: tuple[str, ...] = ()
    expected_events: list[ExpectedEvent] = Field(default_factory=list)
    min_tool_calls: int = 0
    max_tool_calls: int = 100
    expected_handoff: bool = False
    expected_confidence_min: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_terminal_status(self) -> ReplayFixture:
        valid = {"completed", "failed", "waiting_approval", "cancelled", "timeout"}
        if self.terminal_status not in valid:
            raise ValueError(
                f"terminal_status must be one of {valid}, got {self.terminal_status!r}"
            )
        return self
