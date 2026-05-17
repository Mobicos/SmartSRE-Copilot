"""Unit tests for SkillCatalog (built-in SRE skills)."""

from __future__ import annotations

from app.agent_runtime.knowledge_types import SkillManifest
from app.agent_runtime.skill_catalog import BUILTIN_SKILLS, SkillCatalog


def test_builtin_skills_count():
    assert len(BUILTIN_SKILLS) == 7


def test_all_builtin_skills_are_valid_manifests():
    for skill_dict in BUILTIN_SKILLS:
        manifest = SkillManifest(**skill_dict)
        assert manifest.skill_id.startswith("sre-")
        assert len(manifest.diagnostic_steps) >= 3
        assert len(manifest.recommended_tools) >= 2
        assert len(manifest.evidence_requirements) >= 1
        assert len(manifest.risk_warnings) >= 1


def test_match_cpu_high_by_keyword():
    catalog = SkillCatalog()
    matched = catalog.match(scene={}, goal="CPU 使用率过高，负载 95%")
    ids = [s.skill_id for s in matched]
    assert "sre-cpu-high" in ids


def test_match_memory_leak_by_keyword():
    catalog = SkillCatalog()
    matched = catalog.match(scene={}, goal="服务内存持续增长，疑似泄漏")
    ids = [s.skill_id for s in matched]
    assert "sre-memory-leak" in ids


def test_match_disk_full():
    catalog = SkillCatalog()
    matched = catalog.match(scene={}, goal="磁盘空间不足")
    ids = [s.skill_id for s in matched]
    assert "sre-disk-full" in ids


def test_match_slow_response():
    catalog = SkillCatalog()
    matched = catalog.match(scene={}, goal="API 响应延迟 > 5s")
    ids = [s.skill_id for s in matched]
    assert "sre-slow-response" in ids


def test_match_service_unavailable():
    catalog = SkillCatalog()
    matched = catalog.match(scene={}, goal="服务挂了，返回 503")
    ids = [s.skill_id for s in matched]
    assert "sre-service-unavailable" in ids


def test_match_deploy_regression():
    catalog = SkillCatalog()
    matched = catalog.match(scene={}, goal="部署新版本后出现异常")
    ids = [s.skill_id for s in matched]
    assert "sre-deploy-regression" in ids


def test_match_queue_backlog():
    catalog = SkillCatalog()
    matched = catalog.match(scene={}, goal="MQ 消费延迟，队列积压")
    ids = [s.skill_id for s in matched]
    assert "sre-queue-backlog" in ids


def test_no_match_for_unrelated_goal():
    catalog = SkillCatalog()
    matched = catalog.match(scene={}, goal="今天天气怎么样")
    assert len(matched) == 0


def test_get_by_id():
    catalog = SkillCatalog()
    skill = catalog.get("sre-cpu-high")
    assert skill is not None
    assert skill.name == "CPU High Diagnosis"


def test_get_nonexistent_returns_none():
    catalog = SkillCatalog()
    assert catalog.get("sre-nonexistent") is None


def test_custom_skills_appended():
    custom = [
        {
            "skill_id": "custom-test",
            "name": "Test Skill",
            "description": "A test",
            "trigger_conditions": {"keywords": ["custom"], "scene_patterns": []},
            "diagnostic_steps": [{"step": 1, "action": "test"}],
            "recommended_tools": ["TestTool"],
            "evidence_requirements": ["test_data"],
            "risk_warnings": ["none"],
            "report_template": "Report: {goal}",
        }
    ]
    catalog = SkillCatalog(custom_skills=custom)
    assert len(catalog.all_skills) == 8
    skill = catalog.get("custom-test")
    assert skill is not None
