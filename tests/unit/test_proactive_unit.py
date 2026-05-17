"""Unit tests for app.agent_runtime.proactive — monitor, dedup, triggers."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.agent_runtime.proactive import (
    AlertDeduplicator,
    AutoDiagnosisTrigger,
    DegradedMetricProvider,
    InMemoryAlertStore,
    MetricAnomaly,
    ProactiveAlert,
    ProactiveMonitor,
    ProbeResult,
    RedisAlertStore,
)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestMetricAnomaly:
    def test_basic(self):
        a = MetricAnomaly(
            service_name="api",
            metric_type="cpu",
            max_value=95.0,
            threshold=80.0,
            message="CPU spike",
        )
        assert a.alert_key == "api:cpu"

    def test_custom_alert_key(self):
        a = MetricAnomaly(
            service_name="api",
            metric_type="cpu",
            max_value=95.0,
            threshold=80.0,
            message="CPU spike",
            alert_key="custom:key",
        )
        assert a.alert_key == "custom:key"


class TestProactiveAlert:
    def test_basic(self):
        alert = ProactiveAlert(
            alert_key="api:cpu",
            service_name="api",
            metric_type="cpu",
            severity="critical",
            message="CPU spike",
        )
        assert alert.severity == "critical"
        assert alert.run_id is None


class TestProbeResult:
    def test_defaults(self):
        r = ProbeResult(services_polled=2)
        assert r.anomalies == []
        assert r.alerts_emitted == []
        assert r.alerts_suppressed == 0
        assert r.diagnosis_triggered is False


# ---------------------------------------------------------------------------
# InMemoryAlertStore
# ---------------------------------------------------------------------------


class TestInMemoryAlertStore:
    def test_get_returns_none(self):
        store = InMemoryAlertStore()
        assert store.get_last_alert_time("key") is None

    def test_set_and_get(self):
        store = InMemoryAlertStore()
        store.set_last_alert_time("key", 100.0)
        assert store.get_last_alert_time("key") == 100.0


# ---------------------------------------------------------------------------
# AlertDeduplicator
# ---------------------------------------------------------------------------


class TestAlertDeduplicator:
    def test_first_alert_not_suppressed(self):
        store = InMemoryAlertStore()
        dedup = AlertDeduplicator(store=store, clock=lambda: 1000.0)
        assert dedup.should_suppress("key1") is False

    def test_same_time_suppressed(self):
        store = InMemoryAlertStore()
        dedup = AlertDeduplicator(
            store=store, suppress_interval_seconds=300.0, clock=lambda: 1000.0
        )
        dedup.record_alert("key1")
        assert dedup.should_suppress("key1") is True

    def test_outside_window_not_suppressed(self):
        store = InMemoryAlertStore()
        clock_value = [1000.0]
        dedup = AlertDeduplicator(
            store=store,
            suppress_interval_seconds=300.0,
            clock=lambda: clock_value[0],
        )
        dedup.record_alert("key1")
        clock_value[0] = 1400.0  # 400s later, > 300s window
        assert dedup.should_suppress("key1") is False


# ---------------------------------------------------------------------------
# RedisAlertStore
# ---------------------------------------------------------------------------


class TestRedisAlertStore:
    def test_get_returns_none(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        store = RedisAlertStore(mock_redis)
        assert store.get_last_alert_time("key") is None

    def test_get_returns_float(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"123.5"
        store = RedisAlertStore(mock_redis)
        assert store.get_last_alert_time("key") == 123.5

    def test_get_invalid_returns_none(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"not-a-number"
        store = RedisAlertStore(mock_redis)
        assert store.get_last_alert_time("key") is None

    def test_set_calls_setex(self):
        mock_redis = MagicMock()
        store = RedisAlertStore(mock_redis, key_prefix="test:", ttl_seconds=60)
        store.set_last_alert_time("key1", 100.0)
        mock_redis.setex.assert_called_once_with("test:key1", 60, "100.0")


# ---------------------------------------------------------------------------
# DegradedMetricProvider
# ---------------------------------------------------------------------------


class TestDegradedMetricProvider:
    def test_cpu_metrics(self):
        provider = DegradedMetricProvider()
        result = provider.get_cpu_metrics("api-gateway")
        assert result["statistics"]["max"] == 95.0
        assert result["alert_info"]["triggered"] is True
        assert result["_source"] == "degraded_fallback"

    def test_memory_metrics(self):
        provider = DegradedMetricProvider()
        result = provider.get_memory_metrics("api-gateway")
        assert result["statistics"]["max"] == 85.0
        assert result["alert_info"]["triggered"] is True


# ---------------------------------------------------------------------------
# ProactiveMonitor
# ---------------------------------------------------------------------------


class TestProactiveMonitor:
    def _make_provider(self, cpu_max=90.0, mem_max=80.0):
        provider = MagicMock()
        provider.get_cpu_metrics.return_value = {
            "statistics": {"max": cpu_max},
            "alert_info": {"message": "CPU high"},
        }
        provider.get_memory_metrics.return_value = {
            "statistics": {"max": mem_max},
            "alert_info": {"message": "Mem high"},
        }
        return provider

    def test_should_probe_initial(self):
        monitor = ProactiveMonitor(
            metric_provider=self._make_provider(),
            deduplicator=AlertDeduplicator(store=InMemoryAlertStore(), clock=lambda: 0.0),
            services=["api"],
        )
        assert monitor.should_probe() is True

    def test_should_probe_respects_interval(self):
        clock_value = [0.0]

        def clock_fn():
            return clock_value[0]

        monitor = ProactiveMonitor(
            metric_provider=self._make_provider(),
            deduplicator=AlertDeduplicator(store=InMemoryAlertStore(), clock=clock_fn),
            services=[],
            probe_interval_seconds=60.0,
            clock=clock_fn,
        )
        # First probe sets _last_probe_time to current clock
        monitor.probe()
        clock_value[0] = 30.0  # < 60s interval since last probe
        assert monitor.should_probe() is False
        clock_value[0] = 60.0  # exactly 60s
        assert monitor.should_probe() is True

    def test_probe_detects_anomalies(self):
        store = InMemoryAlertStore()
        dedup = AlertDeduplicator(store=store, clock=lambda: 1000.0)
        monitor = ProactiveMonitor(
            metric_provider=self._make_provider(cpu_max=90.0, mem_max=80.0),
            deduplicator=dedup,
            services=["api-gateway"],
            cpu_threshold=80.0,
            memory_threshold=70.0,
        )
        result = monitor.probe()
        assert result.services_polled == 1
        assert len(result.anomalies) == 2
        assert len(result.alerts_emitted) == 2

    def test_probe_suppresses_duplicates(self):
        store = InMemoryAlertStore()
        dedup = AlertDeduplicator(
            store=store, suppress_interval_seconds=300.0, clock=lambda: 1000.0
        )
        monitor = ProactiveMonitor(
            metric_provider=self._make_provider(cpu_max=90.0),
            deduplicator=dedup,
            services=["api"],
            cpu_threshold=80.0,
            memory_threshold=200.0,
        )
        result1 = monitor.probe()
        assert len(result1.alerts_emitted) == 1
        result2 = monitor.probe()
        assert result2.alerts_suppressed == 1
        assert len(result2.alerts_emitted) == 0

    def test_probe_no_anomalies(self):
        monitor = ProactiveMonitor(
            metric_provider=self._make_provider(cpu_max=50.0, mem_max=30.0),
            deduplicator=AlertDeduplicator(store=InMemoryAlertStore(), clock=lambda: 0.0),
            services=["api"],
            cpu_threshold=80.0,
            memory_threshold=70.0,
        )
        result = monitor.probe()
        assert len(result.anomalies) == 0
        assert len(result.alerts_emitted) == 0

    def test_probe_triggers_diagnosis(self):
        mock_trigger = MagicMock()
        mock_trigger.trigger.return_value = "run-123"
        monitor = ProactiveMonitor(
            metric_provider=self._make_provider(cpu_max=90.0),
            deduplicator=AlertDeduplicator(store=InMemoryAlertStore(), clock=lambda: 0.0),
            trigger=mock_trigger,
            services=["api"],
            cpu_threshold=80.0,
            memory_threshold=200.0,
        )
        result = monitor.probe()
        assert result.diagnosis_triggered is True
        assert result.run_id == "run-123"
        mock_trigger.trigger.assert_called_once()

    def test_probe_provider_exception_graceful(self):
        provider = MagicMock()
        provider.get_cpu_metrics.side_effect = RuntimeError("connection refused")
        provider.get_memory_metrics.return_value = {
            "statistics": {"max": 30.0},
            "alert_info": {"triggered": False},
        }
        monitor = ProactiveMonitor(
            metric_provider=provider,
            deduplicator=AlertDeduplicator(store=InMemoryAlertStore(), clock=lambda: 0.0),
            services=["api"],
            cpu_threshold=80.0,
            memory_threshold=70.0,
        )
        result = monitor.probe()
        assert result.services_polled == 1

    def test_anomaly_to_alert_critical(self):
        monitor = ProactiveMonitor(
            metric_provider=self._make_provider(),
            deduplicator=AlertDeduplicator(store=InMemoryAlertStore(), clock=lambda: 0.0),
            services=[],
        )
        anomaly = MetricAnomaly(
            service_name="api",
            metric_type="cpu",
            max_value=96.0,  # >= 80 * 1.2 = 96
            threshold=80.0,
            message="spike",
        )
        alert = monitor._anomaly_to_alert(anomaly)
        assert alert.severity == "critical"

    def test_anomaly_to_alert_warning(self):
        monitor = ProactiveMonitor(
            metric_provider=self._make_provider(),
            deduplicator=AlertDeduplicator(store=InMemoryAlertStore(), clock=lambda: 0.0),
            services=[],
        )
        anomaly = MetricAnomaly(
            service_name="api",
            metric_type="cpu",
            max_value=85.0,  # < 80 * 1.2 = 96
            threshold=80.0,
            message="spike",
        )
        alert = monitor._anomaly_to_alert(anomaly)
        assert alert.severity == "warning"

    def test_degraded_flag(self):
        monitor = ProactiveMonitor(
            metric_provider=self._make_provider(),
            deduplicator=AlertDeduplicator(store=InMemoryAlertStore(), clock=lambda: 0.0),
            services=[],
        )
        assert monitor.is_degraded is False
        monitor.set_degraded(True)
        assert monitor.is_degraded is True


# ---------------------------------------------------------------------------
# AutoDiagnosisTrigger
# ---------------------------------------------------------------------------


class TestAutoDiagnosisTrigger:
    def test_trigger_creates_run(self):
        mock_creator = MagicMock(return_value="run-1")
        trigger = AutoDiagnosisTrigger(
            run_creator=mock_creator,
            scene_id="scene-1",
        )
        anomalies = [
            MetricAnomaly(
                service_name="api",
                metric_type="cpu",
                max_value=90.0,
                threshold=80.0,
                message="CPU high",
            ),
        ]
        run_id = trigger.trigger(service_name="api", anomalies=anomalies)
        assert run_id == "run-1"
        mock_creator.assert_called_once()
        call_args = mock_creator.call_args
        assert call_args[0][0] == "scene-1"
        assert "api" in call_args[0][2]

    def test_trigger_returns_none_on_failure(self):
        mock_creator = MagicMock(return_value=None)
        trigger = AutoDiagnosisTrigger(run_creator=mock_creator, scene_id="s1")
        run_id = trigger.trigger(
            service_name="api",
            anomalies=[
                MetricAnomaly(
                    service_name="api",
                    metric_type="cpu",
                    max_value=90.0,
                    threshold=80.0,
                    message="high",
                ),
            ],
        )
        assert run_id is None
