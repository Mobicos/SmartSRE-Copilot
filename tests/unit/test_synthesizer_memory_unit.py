"""Unit tests for synthesizer, memory_retriever, and memory_extractor."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agent_runtime.memory_extractor import MemoryExtractor
from app.agent_runtime.memory_retriever import MemoryItem, MemoryRetriever
from app.agent_runtime.synthesizer import ReportSynthesizer

# ---------------------------------------------------------------------------
# MemoryItem
# ---------------------------------------------------------------------------


class TestMemoryItem:
    def test_basic(self):
        m = MemoryItem(
            memory_id="m1",
            conclusion_text="OOM root cause",
            conclusion_type="root_cause",
            confidence=0.8,
            validation_count=3,
            similarity=0.92,
        )
        assert m.memory_id == "m1"
        assert m.run_id is None


# ---------------------------------------------------------------------------
# MemoryRetriever
# ---------------------------------------------------------------------------


class TestMemoryRetriever:
    def test_retrieve_empty_query(self):
        embedder = MagicMock()
        store = MagicMock()
        retriever = MemoryRetriever(embedding_provider=embedder, memory_store=store)
        result = retriever.retrieve(workspace_id="ws1", query="   ")
        assert result == []
        embedder.embed_query.assert_not_called()

    def test_retrieve_embedding_failure(self):
        embedder = MagicMock()
        embedder.embed_query.side_effect = RuntimeError("no connection")
        store = MagicMock()
        retriever = MemoryRetriever(embedding_provider=embedder, memory_store=store)
        result = retriever.retrieve(workspace_id="ws1", query="OOM")
        assert result == []

    def test_retrieve_with_results(self):
        embedder = MagicMock()
        embedder.embed_query.return_value = [0.1, 0.2]
        store = MagicMock()
        store.search_memory_vector.return_value = [
            {
                "memory_id": "m1",
                "conclusion_text": "OOM root cause",
                "conclusion_type": "root_cause",
                "confidence": 0.8,
                "validation_count": 3,
                "similarity": 0.92,
                "run_id": "r1",
                "metadata": {"source": "test"},
            },
        ]
        retriever = MemoryRetriever(
            embedding_provider=embedder, memory_store=store, top_k=3, similarity_threshold=0.5
        )
        items = retriever.retrieve(workspace_id="ws1", query="OOM killer active")
        assert len(items) == 1
        assert items[0].memory_id == "m1"
        assert items[0].conclusion_type == "root_cause"
        store.search_memory_vector.assert_called_once_with(
            workspace_id="ws1",
            query_embedding=[0.1, 0.2],
            top_k=3,
            similarity_threshold=0.5,
        )

    def test_retrieve_custom_params(self):
        embedder = MagicMock()
        embedder.embed_query.return_value = [0.1]
        store = MagicMock()
        store.search_memory_vector.return_value = []
        retriever = MemoryRetriever(embedding_provider=embedder, memory_store=store, top_k=5)
        retriever.retrieve(workspace_id="ws1", query="test", top_k=10, similarity_threshold=0.9)
        call_kwargs = store.search_memory_vector.call_args[1]
        assert call_kwargs["top_k"] == 10
        assert call_kwargs["similarity_threshold"] == 0.9


class TestFormatForContext:
    def test_empty(self):
        retriever = MemoryRetriever(embedding_provider=MagicMock(), memory_store=MagicMock())
        assert retriever.format_for_context([]) == ""

    def test_with_memories(self):
        retriever = MemoryRetriever(embedding_provider=MagicMock(), memory_store=MagicMock())
        memories = [
            MemoryItem(
                memory_id="m1",
                conclusion_text="OOM root cause",
                conclusion_type="root_cause",
                confidence=0.8,
                validation_count=3,
                similarity=0.92,
            ),
            MemoryItem(
                memory_id="m2",
                conclusion_text="CPU spike",
                conclusion_type="evidence",
                confidence=0.6,
                validation_count=0,
                similarity=0.75,
            ),
        ]
        ctx = retriever.format_for_context(memories)
        assert "历史经验参考" in ctx
        assert "OOM root cause" in ctx
        assert "已验证 3 次" in ctx
        assert "置信度 80%" in ctx
        assert "CPU spike" in ctx
        assert "历史相似诊断结论，仅供参考" in ctx


# ---------------------------------------------------------------------------
# MemoryExtractor._parse_sections
# ---------------------------------------------------------------------------


class TestParseSections:
    def test_root_cause_section(self):
        extractor = MemoryExtractor(embedding_provider=MagicMock(), memory_store=MagicMock())
        report = "## 根因\n内存泄漏导致 OOM\n## 证据\nSwap used"
        sections = extractor._parse_sections(report)
        assert len(sections) == 2
        assert sections[0][0] == "root_cause"
        assert "内存泄漏" in sections[0][1]
        assert sections[1][0] == "evidence"

    def test_english_sections(self):
        extractor = MemoryExtractor(embedding_provider=MagicMock(), memory_store=MagicMock())
        report = "## Root Cause\nMemory leak\n## Solution\nFix the code"
        sections = extractor._parse_sections(report)
        assert sections[0][0] == "root_cause"
        assert sections[1][0] == "solution"

    def test_no_sections(self):
        extractor = MemoryExtractor(embedding_provider=MagicMock(), memory_store=MagicMock())
        sections = extractor._parse_sections("just some text without sections")
        assert sections == []

    def test_recommendation_section(self):
        extractor = MemoryExtractor(embedding_provider=MagicMock(), memory_store=MagicMock())
        report = "## 建议\nIncrease memory limit"
        sections = extractor._parse_sections(report)
        assert len(sections) == 1
        assert sections[0][0] == "solution"


class TestSectionConfidence:
    def test_root_cause(self):
        assert MemoryExtractor._section_confidence("root_cause") == 0.8

    def test_evidence(self):
        assert MemoryExtractor._section_confidence("evidence") == 0.7

    def test_solution(self):
        assert MemoryExtractor._section_confidence("solution") == 0.75

    def test_final_report(self):
        assert MemoryExtractor._section_confidence("final_report") == 0.5

    def test_unknown(self):
        assert MemoryExtractor._section_confidence("unknown") == 0.5


class TestExtractAndStore:
    def test_stores_sections(self):
        embedder = MagicMock()
        embedder.embed_query.return_value = [0.1, 0.2]
        store = MagicMock()
        store.create_memory_with_embedding.return_value = "mem-1"

        extractor = MemoryExtractor(embedding_provider=embedder, memory_store=store)
        results = extractor.extract_and_store(
            workspace_id="ws1",
            run_id="r1",
            final_report="## 根因\nMemory leak causing OOM\n## 证据\nHigh swap usage detected",
            goal="OOM diagnosis",
        )
        assert len(results) >= 1
        assert store.create_memory_with_embedding.call_count >= 1

    def test_stores_fallback_when_no_sections(self):
        embedder = MagicMock()
        embedder.embed_query.return_value = [0.1]
        store = MagicMock()
        store.create_memory_with_embedding.return_value = "mem-1"

        extractor = MemoryExtractor(embedding_provider=embedder, memory_store=store)
        results = extractor.extract_and_store(
            workspace_id="ws1",
            run_id="r1",
            final_report="Just some text without any sections at all",
            goal="test",
        )
        assert len(results) >= 1

    def test_skips_short_text(self):
        embedder = MagicMock()
        store = MagicMock()
        store.create_memory_with_embedding.return_value = "mem-1"

        extractor = MemoryExtractor(embedding_provider=embedder, memory_store=store)
        results = extractor.extract_and_store(
            workspace_id="ws1",
            run_id="r1",
            final_report="## 根因\nshort",
            goal="",
        )
        assert len(results) == 0

    def test_embedding_failure_stores_empty(self):
        embedder = MagicMock()
        embedder.embed_query.side_effect = RuntimeError("no embedder")
        store = MagicMock()
        store.create_memory_with_embedding.return_value = "mem-1"

        extractor = MemoryExtractor(embedding_provider=embedder, memory_store=store)
        results = extractor.extract_and_store(
            workspace_id="ws1",
            run_id="r1",
            final_report="## 根因\nRoot cause identified with enough text to pass",
            goal="",
        )
        assert len(results) >= 1
        call_kwargs = store.create_memory_with_embedding.call_args[1]
        assert call_kwargs["embedding"] == []


# ---------------------------------------------------------------------------
# ReportSynthesizer
# ---------------------------------------------------------------------------


class TestReportSynthesizer:
    def _make_state(self, **overrides):
        defaults = {
            "goal": "diagnose OOM",
            "evidence": [],
            "knowledge_context": SimpleNamespace(
                to_report_lines=lambda: ["- KB1 (1.0): desc"],
            ),
            "evidence_report_lines": lambda: [],
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_build_report_no_evidence(self):
        state = self._make_state()
        report = ReportSynthesizer.build_report(state)
        assert "SmartSRE Agent 证据报告" in report
        assert "diagnose OOM" in report
        assert "未采集到工具证据" in report
        assert "尚未确认任何事实" in report

    def test_build_report_with_evidence(self):
        evidence = [
            SimpleNamespace(
                tool_name="SearchLog",
                status="success",
                output="OOM found",
                to_report_line=lambda: "SearchLog: OOM found",
            ),
        ]
        state = self._make_state(
            evidence=evidence,
            evidence_report_lines=lambda: ["SearchLog: OOM found"],
        )
        report = ReportSynthesizer.build_report(state)
        assert "SearchLog" in report
        assert "OOM found" in report

    def test_build_report_with_failures(self):
        evidence = [
            SimpleNamespace(
                tool_name="X",
                status="error",
                output=None,
                to_report_line=lambda: "X: tool execution failed: timeout",
            ),
        ]
        state = self._make_state(
            evidence=evidence,
            evidence_report_lines=lambda: ["X: error"],
        )
        report = ReportSynthesizer.build_report(state)
        assert "timeout" in report

    def test_unavailable_report(self):
        report = ReportSynthesizer.unavailable_report("diagnose disk")
        assert "diagnose disk" in report
        assert "外部 MCP 工具不可用" in report

    def test_unavailable_report_with_knowledge(self):
        ctx = SimpleNamespace(to_report_lines=lambda: ["- KB (1.0): test"])
        report = ReportSynthesizer.unavailable_report("fix", knowledge_context=ctx)
        assert "KB" in report

    def test_build_bounded_report(self):
        state = self._make_state()
        report = ReportSynthesizer.build_bounded_report(
            state, max_steps=5, executed_tools=["A"], skipped_tools=["B"]
        )
        assert "执行边界" in report
        assert "最大工具步骤：5" in report
        assert "A" in report
        assert "B" in report
