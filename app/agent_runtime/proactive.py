"""Proactive monitoring: periodic metric probing, alert dedup, auto-diagnosis.

The ProactiveMonitor polls MCP metric tools at a configurable interval,
detects anomalies (CPU spike, memory pressure), deduplicates alerts within
a time window, and optionally triggers an automatic AgentRun for root-cause
analysis.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricAnomaly:
    """A detected anomaly in a probed metric."""

    service_name: str
    metric_type: str  # "cpu" | "memory"
    max_value: float
    threshold: float
    message: str
    alert_key: str = ""  # dedup key, auto-generated if empty

    def __post_init__(self) -> None:
        if not self.alert_key:
            object.__setattr__(
                self,
                "alert_key",
                f"{self.service_name}:{self.metric_type}",
            )


@dataclass(frozen=True)
class ProactiveAlert:
    """An alert ready to be pushed to the frontend."""

    alert_key: str
    service_name: str
    metric_type: str
    severity: str  # "warning" | "critical"
    message: str
    run_id: str | None = None
    timestamp: float = 0.0


@dataclass(frozen=True)
class ProbeResult:
    """Result of one full probe cycle across all services."""

    services_polled: int
    anomalies: list[MetricAnomaly] = field(default_factory=list)
    alerts_emitted: list[ProactiveAlert] = field(default_factory=list)
    alerts_suppressed: int = 0
    diagnosis_triggered: bool = False
    run_id: str | None = None
    degraded: bool = False


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class MetricProvider(Protocol):
    """Interface for fetching metrics from an external source."""

    def get_cpu_metrics(
        self, service_name: str, *, scenario: str = "critical"
    ) -> dict[str, Any]: ...

    def get_memory_metrics(
        self, service_name: str, *, scenario: str = "critical"
    ) -> dict[str, Any]: ...


class AlertStore(Protocol):
    """Persistent alert dedup state (Redis-backed or in-memory)."""

    def get_last_alert_time(self, alert_key: str) -> float | None: ...

    def set_last_alert_time(self, alert_key: str, timestamp: float) -> None: ...


class DiagnosisTrigger(Protocol):
    """Interface for triggering an automatic diagnosis run."""

    def trigger(
        self,
        *,
        service_name: str,
        anomalies: list[MetricAnomaly],
    ) -> str | None:
        """Return run_id if a diagnosis run was created, else None."""


# ---------------------------------------------------------------------------
# AlertDeduplicator
# ---------------------------------------------------------------------------

class AlertDeduplicator:
    """Suppress repeated alerts for the same metric within a time window.

    State is stored via an ``AlertStore`` — in-memory for unit tests,
    Redis-backed for production.
    """

    def __init__(
        self,
        *,
        store: AlertStore,
        suppress_interval_seconds: float = 1800.0,  # 30 minutes
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._store = store
        self._suppress_interval = suppress_interval_seconds
        self._clock = clock or time.monotonic

    def should_suppress(self, alert_key: str) -> bool:
        """Return True if this alert should be suppressed (duplicate within window)."""
        last_time = self._store.get_last_alert_time(alert_key)
        if last_time is None:
            return False
        return (self._clock() - last_time) < self._suppress_interval

    def record_alert(self, alert_key: str) -> None:
        """Record that an alert was emitted for *alert_key*."""
        self._store.set_last_alert_time(alert_key, self._clock())


# ---------------------------------------------------------------------------
# In-memory AlertStore (for tests and single-process deployments)
# ---------------------------------------------------------------------------

class InMemoryAlertStore:
    """In-memory alert dedup store — not shared across processes."""

    def __init__(self) -> None:
        self._state: dict[str, float] = {}

    def get_last_alert_time(self, alert_key: str) -> float | None:
        return self._state.get(alert_key)

    def set_last_alert_time(self, alert_key: str, timestamp: float) -> None:
        self._state[alert_key] = timestamp


# ---------------------------------------------------------------------------
# RedisAlertStore
# ---------------------------------------------------------------------------

class RedisAlertStore:
    """Redis-backed alert dedup store — shared across processes."""

    def __init__(
        self,
        redis_client: Any,
        *,
        key_prefix: str = "proactive:alert:",
        ttl_seconds: int = 3600,
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._ttl = ttl_seconds

    def _key(self, alert_key: str) -> str:
        return f"{self._key_prefix}{alert_key}"

    def get_last_alert_time(self, alert_key: str) -> float | None:
        raw = self._redis.get(self._key(alert_key))
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def set_last_alert_time(self, alert_key: str, timestamp: float) -> None:
        self._redis.setex(self._key(alert_key), self._ttl, str(timestamp))


# ---------------------------------------------------------------------------
# DegradedMetricProvider
# ---------------------------------------------------------------------------

class DegradedMetricProvider:
    """Fallback metric provider using local MCP monitor_server simulation.

    Used when the primary external monitoring data source is unavailable.
    Returns synthetic critical-scenario metrics.
    """

    def get_cpu_metrics(
        self, service_name: str, *, scenario: str = "critical"
    ) -> dict[str, Any]:
        return {
            "service_name": service_name,
            "metric_name": "cpu_usage_percent",
            "statistics": {"avg": 85.0, "max": 95.0, "min": 60.0, "spike_detected": True},
            "alert_info": {
                "triggered": True,
                "threshold": 80.0,
                "message": f"[degraded] CPU spike detected on {service_name}",
            },
            "_source": "degraded_fallback",
        }

    def get_memory_metrics(
        self, service_name: str, *, scenario: str = "critical"
    ) -> dict[str, Any]:
        return {
            "service_name": service_name,
            "metric_name": "memory_usage_percent",
            "statistics": {"avg": 75.0, "max": 85.0, "min": 50.0, "memory_pressure": True},
            "alert_info": {
                "triggered": True,
                "threshold": 70.0,
                "message": f"[degraded] Memory pressure detected on {service_name}",
            },
            "_source": "degraded_fallback",
        }


# ---------------------------------------------------------------------------
# ProactiveMonitor
# ---------------------------------------------------------------------------

class ProactiveMonitor:
    """Periodically probe metrics, deduplicate, and trigger auto-diagnosis.

    Usage::

        monitor = ProactiveMonitor(
            metric_provider=my_mcp_client,
            deduplicator=AlertDeduplicator(store=redis_store),
            trigger=AutoDiagnosisTrigger(runtime, scene_id="..."),
            services=["api-gateway", "order-service"],
        )
        result = monitor.probe()
        if result.alerts_emitted:
            push_sse_alerts(result.alerts_emitted)
    """

    def __init__(
        self,
        *,
        metric_provider: MetricProvider,
        deduplicator: AlertDeduplicator,
        trigger: DiagnosisTrigger | None = None,
        services: list[str] | None = None,
        cpu_threshold: float = 80.0,
        memory_threshold: float = 70.0,
        probe_interval_seconds: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._provider = metric_provider
        self._dedup = deduplicator
        self._trigger = trigger
        self._services = services or []
        self._cpu_threshold = cpu_threshold
        self._memory_threshold = memory_threshold
        self._probe_interval = probe_interval_seconds
        self._clock = clock or time.monotonic
        self._last_probe_time: float = float("-inf")
        self._degraded = False

    @property
    def is_degraded(self) -> bool:
        return self._degraded

    def set_degraded(self, value: bool) -> None:
        self._degraded = value

    def should_probe(self) -> bool:
        """Return True if enough time has passed since the last probe."""
        return (self._clock() - self._last_probe_time) >= self._probe_interval

    def probe(self) -> ProbeResult:
        """Execute one probe cycle across all configured services."""
        self._last_probe_time = self._clock()
        all_anomalies: list[MetricAnomaly] = []
        all_alerts: list[ProactiveAlert] = []
        suppressed = 0
        run_id: str | None = None

        for service in self._services:
            anomalies = self._probe_service(service)
            all_anomalies.extend(anomalies)

            for anomaly in anomalies:
                if self._dedup.should_suppress(anomaly.alert_key):
                    suppressed += 1
                    continue
                alert = self._anomaly_to_alert(anomaly)
                all_alerts.append(alert)
                self._dedup.record_alert(anomaly.alert_key)

        if all_anomalies and self._trigger is not None:
            run_id = self._trigger.trigger(
                service_name=self._services[0] if self._services else "unknown",
                anomalies=all_anomalies,
            )

        return ProbeResult(
            services_polled=len(self._services),
            anomalies=all_anomalies,
            alerts_emitted=all_alerts,
            alerts_suppressed=suppressed,
            diagnosis_triggered=run_id is not None,
            run_id=run_id,
            degraded=self._degraded,
        )

    def _probe_service(self, service_name: str) -> list[MetricAnomaly]:
        anomalies: list[MetricAnomaly] = []

        try:
            cpu = self._provider.get_cpu_metrics(service_name)
        except Exception:
            cpu = {"statistics": {}, "alert_info": {"triggered": False}}

        try:
            mem = self._provider.get_memory_metrics(service_name)
        except Exception:
            mem = {"statistics": {}, "alert_info": {"triggered": False}}

        cpu_stats = cpu.get("statistics", {})
        cpu_max = float(cpu_stats.get("max", 0))
        if cpu_max >= self._cpu_threshold:
            anomalies.append(
                MetricAnomaly(
                    service_name=service_name,
                    metric_type="cpu",
                    max_value=cpu_max,
                    threshold=self._cpu_threshold,
                    message=cpu.get("alert_info", {}).get("message", f"CPU {cpu_max}%"),
                )
            )

        mem_stats = mem.get("statistics", {})
        mem_max = float(mem_stats.get("max", 0))
        if mem_max >= self._memory_threshold:
            anomalies.append(
                MetricAnomaly(
                    service_name=service_name,
                    metric_type="memory",
                    max_value=mem_max,
                    threshold=self._memory_threshold,
                    message=mem.get("alert_info", {}).get(
                        "message", f"Memory {mem_max}%"
                    ),
                )
            )

        return anomalies

    def _anomaly_to_alert(self, anomaly: MetricAnomaly) -> ProactiveAlert:
        severity = "critical" if anomaly.max_value >= anomaly.threshold * 1.2 else "warning"
        return ProactiveAlert(
            alert_key=anomaly.alert_key,
            service_name=anomaly.service_name,
            metric_type=anomaly.metric_type,
            severity=severity,
            message=anomaly.message,
            timestamp=self._clock(),
        )


# ---------------------------------------------------------------------------
# AutoDiagnosisTrigger
# ---------------------------------------------------------------------------

class AutoDiagnosisTrigger:
    """Trigger an automatic AgentRun when an anomaly is detected.

    Uses a callback to create the run — decoupled from the actual
    AgentRuntime for testability.
    """

    def __init__(
        self,
        *,
        run_creator: Callable[[str, str, str], str | None],
        scene_id: str,
        session_prefix: str = "proactive",
    ) -> None:
        """
        Parameters
        ----------
        run_creator :
            ``(scene_id, session_id, goal) -> run_id | None``.
            The callback should create and persist an AgentRun, returning
            the run_id or None on failure.
        scene_id :
            The scene to use for all auto-generated diagnosis runs.
        """
        self._run_creator = run_creator
        self._scene_id = scene_id
        self._session_prefix = session_prefix
        self._run_counter = 0

    def trigger(
        self,
        *,
        service_name: str,
        anomalies: list[MetricAnomaly],
    ) -> str | None:
        self._run_counter += 1
        session_id = f"{self._session_prefix}-{self._run_counter}"
        anomaly_summary = "; ".join(
            f"{a.metric_type}={a.max_value:.0f}%" for a in anomalies
        )
        goal = (
            f"主动探测发现异常：{service_name} 指标异常（{anomaly_summary}），"
            f"请分析根因并给出处置建议。"
        )
        return self._run_creator(self._scene_id, session_id, goal)
