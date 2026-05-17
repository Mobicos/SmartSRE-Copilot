"""Unit tests for pure helper functions in repository modules."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.platform.persistence.repositories.conversation import (
    ConversationMessage,
    build_session_title,
)
from app.platform.persistence.repositories.native_agent import (
    _event_metadata_columns,
    _json_dumps,
    _json_loads,
    _memory_terms,
    _memory_text_score,
    _model_to_dict,
    _optional_int,
    _optional_str,
)

# ---------------------------------------------------------------------------
# _json_dumps / _json_loads
# ---------------------------------------------------------------------------


class TestJsonDumps:
    def test_none_returns_none(self):
        assert _json_dumps(None) is None

    def test_dict_returns_json_string(self):
        result = _json_dumps({"a": 1, "b": "中文"})
        assert '"a": 1' in result
        assert "中文" in result


class TestJsonLoads:
    def test_none_returns_empty(self):
        assert _json_loads(None) == {}

    def test_empty_string_returns_empty(self):
        assert _json_loads("") == {}

    def test_valid_json_dict(self):
        assert _json_loads('{"x": 1}') == {"x": 1}

    def test_non_dict_json_returns_empty(self):
        assert _json_loads("[1, 2, 3]") == {}

    def test_invalid_json_raises(self):
        import json as _json

        with pytest.raises(_json.JSONDecodeError):
            _json_loads("not-json")


# ---------------------------------------------------------------------------
# _optional_int / _optional_str
# ---------------------------------------------------------------------------


class TestOptionalInt:
    def test_none_returns_none(self):
        assert _optional_int(None) is None

    def test_int_passthrough(self):
        assert _optional_int(42) == 42

    def test_string_int(self):
        assert _optional_int("42") == 42

    def test_invalid_returns_none(self):
        assert _optional_int("abc") is None

    def test_type_error_returns_none(self):
        assert _optional_int([1, 2]) is None


class TestOptionalStr:
    def test_none_returns_none(self):
        assert _optional_str(None) is None

    def test_empty_returns_none(self):
        assert _optional_str("") is None

    def test_nonempty_passthrough(self):
        assert _optional_str("hello") == "hello"

    def test_non_string_coerced(self):
        assert _optional_str(123) == "123"


# ---------------------------------------------------------------------------
# _event_metadata_columns
# ---------------------------------------------------------------------------


class TestEventMetadataColumns:
    def test_none_returns_defaults(self):
        result = _event_metadata_columns(None)
        assert result["step_index"] is None
        assert result["evidence_quality"] is None

    def test_empty_dict(self):
        result = _event_metadata_columns({})
        assert result["step_index"] is None
        assert result["token_usage"] is None

    def test_full_payload(self):
        payload = {
            "step_index": 2,
            "evidence_quality": "strong",
            "recovery_action": "retry",
            "token_usage": {"prompt": 100},
            "cost_estimate": {"total": 0.05},
        }
        result = _event_metadata_columns(payload)
        assert result["step_index"] == 2
        assert result["evidence_quality"] == "strong"
        assert result["recovery_action"] == "retry"
        assert result["token_usage"] == {"prompt": 100}
        assert result["cost_estimate"] == {"total": 0.05}

    def test_nested_decision_evidence(self):
        payload = {
            "decision": {
                "evidence": {
                    "quality": "weak",
                },
            },
        }
        result = _event_metadata_columns(payload)
        assert result["evidence_quality"] == "weak"

    def test_non_dict_token_usage_ignored(self):
        payload = {"token_usage": "invalid"}
        result = _event_metadata_columns(payload)
        assert result["token_usage"] is None

    def test_step_index_from_string(self):
        payload = {"step_index": "3"}
        result = _event_metadata_columns(payload)
        assert result["step_index"] == 3

    def test_evidence_quality_fallback_to_quality_key(self):
        payload = {"quality": "partial"}
        result = _event_metadata_columns(payload)
        assert result["evidence_quality"] == "partial"


# ---------------------------------------------------------------------------
# _memory_text_score / _memory_terms
# ---------------------------------------------------------------------------


class TestMemoryTerms:
    def test_english_words(self):
        terms = _memory_terms("hello world")
        assert "hello" in terms
        assert "world" in terms

    def test_filters_short_terms(self):
        terms = _memory_terms("a bb ccc")
        assert "a" not in terms
        assert "bb" in terms
        assert "ccc" in terms

    def test_chinese_characters(self):
        # Chinese chars are alnum → NOT replaced with spaces
        # Entire string becomes one multi-char term
        terms = _memory_terms("内存泄漏")
        assert "内存泄漏" in terms

    def test_mixed_content(self):
        terms = _memory_terms("OOM killer 活跃")
        assert "oom" in terms
        assert "killer" in terms


class TestMemoryTextScore:
    def test_identical_query_text(self):
        score = _memory_text_score("memory leak issue", "memory leak issue")
        assert score == 1.0

    def test_partial_overlap(self):
        score = _memory_text_score("memory leak detection", "memory leak found")
        assert 0.0 < score < 1.0

    def test_no_overlap(self):
        score = _memory_text_score("CPU usage rate", "disk space full")
        assert score == 0.0

    def test_empty_query(self):
        assert _memory_text_score("", "something") == 0.0

    def test_empty_text(self):
        assert _memory_text_score("query", "") == 0.0


# ---------------------------------------------------------------------------
# _model_to_dict
# ---------------------------------------------------------------------------


class TestModelToDict:
    def test_filters_sa_instance_state(self):
        obj = SimpleNamespace(
            name="test",
            value=42,
            _sa_instance_state="should be filtered",
        )
        result = _model_to_dict(obj)
        assert result == {"name": "test", "value": 42}
        assert "_sa_instance_state" not in result


# ---------------------------------------------------------------------------
# build_session_title
# ---------------------------------------------------------------------------


class TestBuildSessionTitle:
    def test_normal_question(self):
        title = build_session_title("什么是 OOM killer?")
        assert title == "什么是 OOM killer?"

    def test_long_question_truncated(self):
        long_q = "这" * 31 + "短"
        title = build_session_title(long_q)
        assert len(title) == 33  # 30 chars + "..."
        assert title.endswith("...")

    def test_empty_returns_default(self):
        assert build_session_title("") == "新对话"

    def test_whitespace_only(self):
        assert build_session_title("   ") == "新对话"

    def test_exactly_30_chars(self):
        q = "a" * 30
        title = build_session_title(q)
        assert title == q
        assert not title.endswith("...")


# ---------------------------------------------------------------------------
# ConversationMessage.to_dict
# ---------------------------------------------------------------------------


class TestConversationMessageToDict:
    def test_to_dict(self):
        msg = ConversationMessage(role="user", content="hello", timestamp="2024-01-01")
        assert msg.to_dict() == {
            "role": "user",
            "content": "hello",
            "timestamp": "2024-01-01",
        }
