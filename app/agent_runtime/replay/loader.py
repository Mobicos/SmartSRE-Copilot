"""Load replay fixtures from JSON files in the fixtures directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agent_runtime.replay.fixture_schema import ReplayFixture

_FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "tests" / "agent_scenarios" / "fixtures"


def load_fixtures(*, fixtures_dir: Path | None = None) -> list[ReplayFixture]:
    directory = fixtures_dir or _FIXTURES_DIR
    fixtures: list[ReplayFixture] = []
    if not directory.is_dir():
        return fixtures
    for path in sorted(directory.glob("*.json")):
        raw: dict[str, Any] = json.loads(path.read_text())
        fixtures.append(ReplayFixture(**raw))
    return fixtures


def load_fixture_by_id(
    fixture_id: str, *, fixtures_dir: Path | None = None
) -> ReplayFixture | None:
    for fixture in load_fixtures(fixtures_dir=fixtures_dir):
        if fixture.fixture_id == fixture_id:
            return fixture
    return None
