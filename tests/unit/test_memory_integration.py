"""Integration test: full cross-session memory cycle (T053)."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.decision import (
    AgentDecisionState,
    AgentGoalContract,
)
from app.agent_runtime.loop import BoundedReActLoop, LoopBudget
from app.agent_runtime.memory_extractor import MemoryExtractor
from app.agent_runtime.memory_retriever import MemoryRetriever

# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


class _EmbeddingProvider:
    """Deterministic embedding based on text hash."""

    def __init__(self, dim: int = 1024) -> None:
        self._dim = dim
        self.calls: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        h = hash(text) % 1000
        return [float(h + i) / 1000.0 for i in range(self._dim)]


class _MemoryStore:
    """In-memory store simulating pgvector search."""

    def __init__(self) -> None:
        self.memories: list[dict[str, Any]] = []
        self._counter = 0

    def create_memory_with_embedding(
        self,
        *,
        workspace_id: str,
        run_id: str | None,
        conclusion_text: str,
        embedding: list[float],
        conclusion_type: str = "final_report",
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        self._counter += 1
        mid = f"mem-{self._counter:03d}"
        self.memories.append(
            {
                "memory_id": mid,
                "workspace_id": workspace_id,
                "run_id": run_id,
                "conclusion_text": conclusion_text,
                "conclusion_type": conclusion_type,
                "confidence": confidence,
                "validation_count": 0,
                "metadata": metadata or {},
                "embedding": embedding,
            }
        )
        return mid

    def search_memory_vector(
        self,
        *,
        workspace_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        similarity_threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for m in self.memories:
            if m["workspace_id"] != workspace_id:
                continue
            if not m.get("embedding"):
                continue
            sim = _cosine(query_embedding, m["embedding"])
            if sim >= similarity_threshold:
                results.append({**m, "similarity": sim})
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def increment_validation_count(
        self, *, memory_id: str, confidence_boost: float = 0.1
    ) -> dict[str, Any] | None:
        for m in self.memories:
            if m["memory_id"] == memory_id:
                m["validation_count"] += 1
                m["confidence"] = min(m["confidence"] + confidence_boost, 1.0)
                return dict(m)
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _fake_embedding(text: str, dim: int = 1024) -> list[float]:
    h = hash(text) % 1000
    return [float(h + i) / 1000.0 for i in range(dim)]


# ---------------------------------------------------------------------------
# Full memory cycle integration test
# ---------------------------------------------------------------------------


class TestMemoryFullCycle:
    def test_extract_then_retrieve_then_inject(self):
        """
        Full cycle:
        1. Run #1 produces a final report → MemoryExtractor stores conclusions
        2. Run #2 starts with similar goal → MemoryRetriever finds historical memory
        3. BoundedReActLoop injects memory_context into state
        """
        store = _MemoryStore()
        embedder = _EmbeddingProvider()

        # --- Step 1: extract memories from run #1's report ---
        extractor = MemoryExtractor(embedding_provider=embedder, memory_store=store)
        report = (
            "# 诊断报告\n\n"
            "## 根因\n\n"
            "OOM killer 由内存泄漏触发，worker 进程占用 95% 内存。\n\n"
            "## 证据\n\n"
            "CPU 92%，内存 87%。\n\n"
            "## 解决方案\n\n"
            "重启服务并修复内存泄漏代码。"
        )
        stored = extractor.extract_and_store(
            workspace_id="ws-1",
            run_id="run-1",
            final_report=report,
            goal="diagnose OOM",
        )
        assert len(stored) == 3
        assert len(store.memories) == 3

        # --- Step 2: retrieve with matching embedding for run #2's goal ---
        # Store the exact embedding that the retriever will produce for the query
        goal_query = "diagnose OOM memory leak"
        store.create_memory_with_embedding(
            workspace_id="ws-1",
            run_id="run-1",
            conclusion_text="OOM root cause: memory leak in worker",
            embedding=_fake_embedding(goal_query),
            conclusion_type="root_cause",
            confidence=0.85,
        )

        retriever = MemoryRetriever(
            embedding_provider=_EmbeddingProvider(),
            memory_store=store,
            similarity_threshold=0.5,
        )
        memories = retriever.retrieve(workspace_id="ws-1", query=goal_query)
        assert len(memories) >= 1
        assert memories[0].conclusion_type == "root_cause"

        context_str = retriever.format_for_context(memories)
        assert "历史经验参考" in context_str
        assert "OOM" in context_str

        # --- Step 3: loop injects memory context on first step ---
        class _TerminalProvider:
            provider_name = "test"

            def decide(self, state):
                from app.agent_runtime.decision import AgentDecision, EvidenceAssessment

                return AgentDecision(
                    action_type="final_report",
                    selected_tool=None,
                    reasoning_summary="done",
                    evidence=EvidenceAssessment(quality="strong"),
                    confidence=0.9,
                )

        loop = BoundedReActLoop(
            provider=_TerminalProvider(),
            memory_retriever=retriever,
        )
        state = AgentDecisionState(
            run_id="run-2",
            goal=AgentGoalContract(goal=goal_query, workspace_id="ws-1"),
        )
        result = loop.run(state, LoopBudget(max_steps=2, max_time_seconds=30))

        assert result.termination_reason == "final_report"
        assert "历史经验参考" in result.state.memory_context
        assert "OOM" in result.state.memory_context

    def test_memory_validation_boosts_confidence(self):
        """After retrieval, validating a memory boosts its confidence."""
        store = _MemoryStore()
        mem_id = store.create_memory_with_embedding(
            workspace_id="ws-1",
            run_id="run-1",
            conclusion_text="connection pool exhausted",
            embedding=[0.5] * 1024,
            confidence=0.7,
        )
        # First validation
        result = store.increment_validation_count(memory_id=mem_id, confidence_boost=0.1)
        assert result is not None
        assert result["validation_count"] == 1
        assert abs(result["confidence"] - 0.8) < 0.01
        # Second validation — cap at 1.0
        result = store.increment_validation_count(memory_id=mem_id, confidence_boost=0.5)
        assert result["confidence"] == 1.0

    def test_empty_store_returns_no_context(self):
        """With no memories stored, loop runs without memory_context."""
        store = _MemoryStore()
        retriever = MemoryRetriever(
            embedding_provider=_EmbeddingProvider(),
            memory_store=store,
        )

        class _TerminalProvider:
            provider_name = "test"

            def decide(self, state):
                from app.agent_runtime.decision import AgentDecision, EvidenceAssessment

                return AgentDecision(
                    action_type="final_report",
                    selected_tool=None,
                    reasoning_summary="done",
                    evidence=EvidenceAssessment(quality="strong"),
                    confidence=0.9,
                )

        loop = BoundedReActLoop(
            provider=_TerminalProvider(),
            memory_retriever=retriever,
        )
        state = AgentDecisionState(
            run_id="run-empty",
            goal=AgentGoalContract(goal="check system", workspace_id="ws-1"),
        )
        result = loop.run(state, LoopBudget(max_steps=1, max_time_seconds=10))
        assert result.state.memory_context == ""

    def test_embedding_failure_graceful_degradation(self):
        """If embedding service fails, retrieval returns empty, loop continues."""

        class _FailingEmbedder:
            def embed_query(self, text: str) -> list[float]:
                raise ConnectionError("embedding service down")

        store = _MemoryStore()
        retriever = MemoryRetriever(
            embedding_provider=_FailingEmbedder(),
            memory_store=store,
        )

        class _TerminalProvider:
            provider_name = "test"

            def decide(self, state):
                from app.agent_runtime.decision import AgentDecision, EvidenceAssessment

                return AgentDecision(
                    action_type="final_report",
                    selected_tool=None,
                    reasoning_summary="done",
                    evidence=EvidenceAssessment(quality="strong"),
                    confidence=0.9,
                )

        loop = BoundedReActLoop(
            provider=_TerminalProvider(),
            memory_retriever=retriever,
        )
        state = AgentDecisionState(
            run_id="run-fail",
            goal=AgentGoalContract(goal="test", workspace_id="ws-1"),
        )
        result = loop.run(state, LoopBudget(max_steps=1, max_time_seconds=10))
        assert result.termination_reason == "final_report"
        assert result.state.memory_context == ""
