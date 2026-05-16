"""Typed runtime events for Native Agent runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EVENT_PROACTIVE_ALERT = "proactive_alert"


@dataclass(frozen=True)
class AgentRuntimeEvent:
    """Runtime event emitted by the Native Agent loop."""

    type: str
    stage: str
    run_id: str
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    status: str | None = None
    final_report: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to the API-compatible event shape."""
        data: dict[str, Any] = {
            "type": self.type,
            "stage": self.stage,
            "run_id": self.run_id,
        }
        if self.message:
            data["message"] = self.message
        if self.payload:
            data["payload"] = self.payload
        if self.status is not None:
            data["status"] = self.status
        if self.final_report is not None:
            data["final_report"] = self.final_report
        return data


def proactive_alert_event(
    *,
    run_id: str,
    service_name: str,
    metric_type: str,
    severity: str,
    message: str,
    run_id_diagnosis: str | None = None,
    alert_key: str = "",
) -> AgentRuntimeEvent:
    """Create a proactive alert SSE event."""
    return AgentRuntimeEvent(
        type=EVENT_PROACTIVE_ALERT,
        stage="monitoring",
        run_id=run_id,
        message=message,
        payload={
            "service_name": service_name,
            "metric_type": metric_type,
            "severity": severity,
            "alert_key": alert_key,
            "diagnosis_run_id": run_id_diagnosis,
        },
    )
