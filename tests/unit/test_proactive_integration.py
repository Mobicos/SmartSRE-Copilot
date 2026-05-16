"""Integration test: full proactive monitoring flow (T045)."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.proactive import (
    AlertDeduplicator,
    AutoDiagnosisTrigger,
    InMemoryAlertStore,
    ProactiveMonitor,
)

# ---------------------------------------------------------------------------
# Fake metric provider returning critical metrics
# ---------------------------------------------------------------------------


class _CriticalMetricProvider:
    """Returns metrics above default thresholds for both CPU and memory."""

    def get_cpu_metrics(self, service_name: str, **_: Any) -> dict[str, Any]:
        return {
            "service_name": service_name,
            "metric_name": "cpu_usage_percent",
            "statistics": {"avg": 90.0, "max": 95.0, "min": 80.0, "spike_detected": True},
            "alert_info": {
                "triggered": True,
                "threshold": 80.0,
                "message": f"CPU spike detected on {service_name}",
            },
        }

    def get_memory_metrics(self, service_name: str, **_: Any) -> dict[str, Any]:
        return {
            "service_name": service_name,
            "metric_name": "memory_usage_percent",
            "statistics": {"avg": 80.0, "max": 88.0, "min": 70.0, "memory_pressure": True},
            "alert_info": {
                "triggered": True,
                "threshold": 70.0,
                "message": f"Memory pressure on {service_name}",
            },
        }


class _HealthyMetricProvider:
    """Returns metrics below all thresholds."""

    def get_cpu_metrics(self, service_name: str, **_: Any) -> dict[str, Any]:
        return {
            "service_name": service_name,
            "statistics": {"avg": 30.0, "max": 45.0, "min": 20.0},
            "alert_info": {"triggered": False},
        }

    def get_memory_metrics(self, service_name: str, **_: Any) -> dict[str, Any]:
        return {
            "service_name": service_name,
            "statistics": {"avg": 40.0, "max": 55.0, "min": 30.0},
            "alert_info": {"triggered": False},
        }


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestProactiveFullFlow:
    def test_critical_metrics_trigger_alert_and_diagnosis(self):
        """CPU > 80% and memory > 70% → anomalies detected, alert emitted, diagnosis triggered."""
        store = InMemoryAlertStore()
        dedup = AlertDeduplicator(store=store, suppress_interval_seconds=0)
        triggered_runs: list[tuple[str, str, str]] = []

        def _create_run(scene_id: str, session_id: str, goal: str) -> str:
            triggered_runs.append((scene_id, session_id, goal))
            return "run-proactive-001"

        trigger = AutoDiagnosisTrigger(run_creator=_create_run, scene_id="scene-1")

        monitor = ProactiveMonitor(
            metric_provider=_CriticalMetricProvider(),
            deduplicator=dedup,
            trigger=trigger,
            services=["api-gateway", "order-service"],
            probe_interval_seconds=0,
        )

        result = monitor.probe()

        # Both services × 2 metrics = 4 anomalies
        assert len(result.anomalies) == 4
        assert len(result.alerts_emitted) == 4
        assert result.diagnosis_triggered is True
        assert result.run_id == "run-proactive-001"
        assert len(triggered_runs) == 1
        assert triggered_runs[0][0] == "scene-1"
        assert result.services_polled == 2

    def test_healthy_metrics_no_alert(self):
        """Metrics below threshold → no anomalies, no alerts."""
        monitor = ProactiveMonitor(
            metric_provider=_HealthyMetricProvider(),
            deduplicator=AlertDeduplicator(store=InMemoryAlertStore()),
            services=["api-gateway"],
            probe_interval_seconds=0,
        )
        result = monitor.probe()
        assert len(result.anomalies) == 0
        assert len(result.alerts_emitted) == 0
        assert result.diagnosis_triggered is False

    def test_deduplication_suppresses_duplicate_alerts(self):
        """Same alert within suppress window → second probe suppressed."""
        store = InMemoryAlertStore()
        dedup = AlertDeduplicator(store=store, suppress_interval_seconds=3600)
        monitor = ProactiveMonitor(
            metric_provider=_CriticalMetricProvider(),
            deduplicator=dedup,
            services=["api-gateway"],
            probe_interval_seconds=0,
        )

        result1 = monitor.probe()
        assert len(result1.alerts_emitted) == 2  # cpu + memory

        result2 = monitor.probe()
        assert len(result2.alerts_emitted) == 0
        assert result2.alerts_suppressed == 2

    def test_degraded_provider_still_probes(self):
        """Degraded mode: provider returns synthetic critical metrics."""
        from app.agent_runtime.proactive import DegradedMetricProvider

        monitor = ProactiveMonitor(
            metric_provider=DegradedMetricProvider(),
            deduplicator=AlertDeduplicator(store=InMemoryAlertStore(), suppress_interval_seconds=0),
            services=["api-gateway"],
            probe_interval_seconds=0,
        )
        monitor.set_degraded(True)
        result = monitor.probe()
        assert result.degraded is True
        assert len(result.anomalies) >= 1

    def test_probe_interval_enforced(self):
        """Second probe within interval → should_probe=False, probe still runs."""
        clock_value = [0.0]

        def _clock() -> float:
            return clock_value[0]

        monitor = ProactiveMonitor(
            metric_provider=_HealthyMetricProvider(),
            deduplicator=AlertDeduplicator(store=InMemoryAlertStore()),
            services=["api-gateway"],
            probe_interval_seconds=60.0,
            clock=_clock,
        )

        assert monitor.should_probe() is True
        monitor.probe()

        clock_value[0] = 30.0
        assert monitor.should_probe() is False

        clock_value[0] = 61.0
        assert monitor.should_probe() is True

    def test_failing_metric_provider_does_not_crash(self):
        """If get_cpu_metrics raises, probe continues with remaining services."""

        class _FailingProvider:
            def get_cpu_metrics(self, service_name: str, **_: Any) -> dict[str, Any]:
                raise ConnectionError("monitoring down")

            def get_memory_metrics(self, service_name: str, **_: Any) -> dict[str, Any]:
                return {
                    "statistics": {"max": 90.0},
                    "alert_info": {"triggered": True, "message": "mem high"},
                }

        monitor = ProactiveMonitor(
            metric_provider=_FailingProvider(),
            deduplicator=AlertDeduplicator(store=InMemoryAlertStore(), suppress_interval_seconds=0),
            services=["api-gateway"],
            probe_interval_seconds=0,
        )
        result = monitor.probe()
        # CPU failed but memory still detected
        assert len(result.anomalies) == 1
        assert result.anomalies[0].metric_type == "memory"
