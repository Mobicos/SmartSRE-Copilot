from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.agent_runtime.metrics_collector import MetricsCollector
from app.core.config import AppSettings


class _RunStore:
    def __init__(self) -> None:
        created_at = datetime.now(UTC)
        self.run = {
            "run_id": "run-1",
            "goal": "diagnose latency",
            "session_id": "session-1",
            "status": "completed",
            "final_report": "Latency was caused by upstream 5xx spikes.",
            "created_at": created_at,
            "updated_at": created_at + timedelta(milliseconds=250),
        }
        self.events = [
            {
                "type": "decision",
                "payload": {
                    "decision": {"action_type": "final_report"},
                    "token_usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 8,
                        "total": 20,
                        "source": "provider_usage",
                    },
                    "cost_estimate": {
                        "currency": "USD",
                        "total_cost": 0.0012,
                        "source": "provider_usage",
                    },
                },
            },
            {"type": "tool_call", "payload": {"tool": "SearchLog"}},
            {"type": "knowledge_context", "payload": {"citations": []}},
        ]
        self.persisted: dict[str, Any] | None = None

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.run if run_id == "run-1" else None

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        return list(self.events) if run_id == "run-1" else []

    def update_run_metrics(self, run_id: str, **metrics: Any) -> None:
        self.persisted = metrics


def test_metrics_collector_prefers_provider_token_and_cost_events():
    run_store = _RunStore()
    collector = MetricsCollector(
        run_store,  # type: ignore[arg-type]
        AppSettings(agent_decision_provider="qwen", dashscope_model="qwen-max"),
    )

    metrics = collector.collect_run_metrics("run-1")
    collector.persist("run-1")

    assert metrics is not None
    assert metrics["model_name"] == "qwen-max"
    assert metrics["decision_provider"] == "qwen"
    assert metrics["step_count"] == 2
    assert metrics["tool_call_count"] == 1
    assert metrics["retrieval_count"] == 1
    assert metrics["latency_ms"] == 250
    assert metrics["token_usage"] == {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "tool_output_tokens": 0,
        "total": 20,
        "model": "qwen-max",
        "source": "provider_usage",
    }
    assert metrics["cost_estimate"] == {
        "currency": "USD",
        "total_cost": 0.0012,
        "model": "qwen-max",
        "source": "provider_usage",
        "components": {
            "tokens": 20,
            "tool_calls": 1,
            "retrievals": 1,
        },
    }
    assert run_store.persisted == metrics
