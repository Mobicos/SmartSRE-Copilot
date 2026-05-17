"""OpenTelemetry tracing helpers for Native Agent runtime boundaries."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any, Protocol


class TraceSpan(Protocol):
    """Minimal span interface used by runtime modules."""

    def set_attribute(self, key: str, value: Any) -> None:
        """Attach one attribute to the current span."""


class NoopTraceSpan:
    """Span used when OpenTelemetry is unavailable."""

    def set_attribute(self, key: str, value: Any) -> None:
        return None


class TraceCollector:
    """Create optional spans without making tracing a hard runtime dependency."""

    def __init__(self, tracer_name: str = "smartsre.agent_runtime") -> None:
        self._tracer_name = tracer_name

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[TraceSpan]:
        try:
            from opentelemetry import trace
        except Exception:
            with nullcontext():
                yield NoopTraceSpan()
            return

        with trace.get_tracer(self._tracer_name).start_as_current_span(name) as span:
            for key, value in (attributes or {}).items():
                span.set_attribute(key, value)
            yield span

    def gen_ai_span(
        self,
        name: str,
        *,
        model: str = "",
        operation: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        run_id: str = "",
        **extra: Any,
    ) -> Iterator[TraceSpan]:
        """Create a span aligned with OpenTelemetry GenAI semantic conventions."""
        attrs: dict[str, Any] = {
            "gen_ai.operation.name": operation or name,
            "gen_ai.request.model": model,
            "gen_ai.response.model": model,
            "gen_ai.usage.input_tokens": input_tokens,
            "gen_ai.usage.output_tokens": output_tokens,
            "agent.run_id": run_id,
        }
        attrs.update(extra)
        return self.span(name, attributes=attrs)
