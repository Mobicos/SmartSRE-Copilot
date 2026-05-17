"""Miscellaneous small coverage targets: schemas, compat, logger, database."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domains.aiops.schemas import AIOpsRequest
from app.platform.compat import stabilize_windows_platform_detection

# ---------------------------------------------------------------------------
# AIOpsRequest
# ---------------------------------------------------------------------------


class TestAIOpsRequest:
    def test_diagnosis_goal_goal(self):
        req = AIOpsRequest(goal="CPU spike")
        assert req.diagnosis_goal() == "CPU spike"

    def test_diagnosis_goal_query(self):
        req = AIOpsRequest(query="what's wrong")
        assert req.diagnosis_goal() == "what's wrong"

    def test_diagnosis_goal_question(self):
        req = AIOpsRequest(question="help me")
        assert req.diagnosis_goal() == "help me"

    def test_diagnosis_goal_problem(self):
        req = AIOpsRequest(problem="memory leak")
        assert req.diagnosis_goal() == "memory leak"

    def test_diagnosis_goal_none(self):
        req = AIOpsRequest()
        assert req.diagnosis_goal() is None

    def test_diagnosis_goal_whitespace(self):
        req = AIOpsRequest(goal="   ")
        assert req.diagnosis_goal() is None

    def test_diagnosis_goal_strips(self):
        req = AIOpsRequest(goal="  CPU high  ")
        assert req.diagnosis_goal() == "CPU high"

    def test_default_session_id(self):
        req = AIOpsRequest()
        assert req.session_id == "default"

    def test_alias_session_id(self):
        req = AIOpsRequest(sessionId="custom")
        assert req.session_id == "custom"


# ---------------------------------------------------------------------------
# stabilize_windows_platform_detection
# ---------------------------------------------------------------------------


class TestStabilizeWindowsPlatform:
    def test_non_windows_noop(self):
        with patch("app.platform.compat.sys") as mock_sys:
            mock_sys.platform = "darwin"
            stabilize_windows_platform_detection()  # should not modify platform

    def test_windows_sets_machine(self):
        import platform as _platform

        original_machine = _platform.machine
        try:
            with patch("app.platform.compat.sys") as mock_sys:
                mock_sys.platform = "win32"
                with patch.dict("os.environ", {"PROCESSOR_ARCHITECTURE": "ARM64"}):
                    stabilize_windows_platform_detection()
                    assert _platform.machine() == "ARM64"
        finally:
            _platform.machine = original_machine

    def test_windows_no_env(self):
        import platform as _platform

        original_machine = _platform.machine
        try:
            with patch("app.platform.compat.sys") as mock_sys:
                mock_sys.platform = "win32"
                with patch.dict("os.environ", {}, clear=True):
                    stabilize_windows_platform_detection()
                    assert _platform.machine() == "AMD64"
        finally:
            _platform.machine = original_machine


# ---------------------------------------------------------------------------
# database.get_db
# ---------------------------------------------------------------------------


class TestGetDb:
    def test_get_db_yields_session(self):
        from app.platform.persistence.database import get_db

        mock_session = MagicMock()
        with patch("app.platform.persistence.database.get_engine"):
            with patch("app.platform.persistence.database.Session") as MockSession:
                MockSession.return_value = mock_session
                gen = get_db()
                session = next(gen)
                assert session is mock_session
                # Send None to simulate normal completion
                try:
                    gen.send(None)
                except StopIteration:
                    pass
                mock_session.commit.assert_called_once()
                mock_session.close.assert_called_once()

    def test_get_db_rollback_on_exception(self):
        from app.platform.persistence.database import get_db

        mock_session = MagicMock()
        with patch("app.platform.persistence.database.get_engine"):
            with patch("app.platform.persistence.database.Session") as MockSession:
                MockSession.return_value = mock_session
                gen = get_db()
                next(gen)
                # Send exception
                with pytest.raises(RuntimeError):
                    gen.throw(RuntimeError, "db error", None)
                mock_session.rollback.assert_called_once()
                mock_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# setup_logger OSError fallback
# ---------------------------------------------------------------------------


class TestSetupLogger:
    def test_oserror_fallback(self):
        from app.utils.logger import setup_logger

        call_count = [0]

        def _mock_add(sink, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                # Second logger.add call raises OSError (file sink with enqueue=True)
                raise OSError("queue not available")

        with patch("app.utils.logger.logger") as mock_logger:
            mock_logger.add.side_effect = _mock_add
            mock_logger.remove = MagicMock()
            mock_logger.configure = MagicMock()
            with patch("app.utils.logger.LOGS_DIR"):
                with patch("app.utils.logger.config") as mock_config:
                    mock_config.debug = False
                    mock_config.is_production = False
                    setup_logger()
                    # 1st add (stdout) succeeds, 2nd (file enqueue=True) raises OSError,
                    # 3rd add (file enqueue=False fallback) succeeds
                    assert mock_logger.add.call_count == 3
