"""Built-in SRE skill catalog — 7 diagnostic skill manifests."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.knowledge_types import SkillManifest

BUILTIN_SKILLS: list[dict[str, Any]] = [
    {
        "skill_id": "sre-cpu-high",
        "name": "CPU High Diagnosis",
        "description": "Diagnose sustained high CPU usage on a host or service instance.",
        "trigger_conditions": {
            "keywords": ["cpu", "cpu高", "cpu高负载", "cpu负载高", "cpu usage"],
            "scene_patterns": ["cpu_alert", "performance"],
        },
        "diagnostic_steps": [
            {
                "step": 1,
                "action": "check_cpu_usage",
                "description": "获取当前 CPU 使用率和 load average",
            },
            {"step": 2, "action": "list_processes", "description": "列出占用 CPU 最高的进程"},
            {"step": 3, "action": "check_gc", "description": "检查 GC 暂停和频率"},
            {"step": 4, "action": "check_cron", "description": "排查是否有定时任务争抢 CPU"},
        ],
        "recommended_tools": ["GetMetrics", "GetProcessInfo", "SearchLog", "GetCPUUsage"],
        "evidence_requirements": ["cpu_usage_percent", "load_average", "top_processes"],
        "risk_warnings": [
            "避免直接 kill 主进程导致服务中断",
            "关注 load average 是否持续升高",
            "区分 user time 和 system time",
        ],
        "report_template": (
            "## CPU 高负载诊断报告\n\n"
            "**现象**: {goal}\n\n"
            "**根因**: {root_cause}\n\n"
            "**证据**:\n{evidence}\n\n"
            "**建议**:\n{recommendations}\n"
        ),
    },
    {
        "skill_id": "sre-memory-leak",
        "name": "Memory Leak Diagnosis",
        "description": "Detect and diagnose memory leak patterns in services.",
        "trigger_conditions": {
            "keywords": ["内存", "memory", "oom", "内存泄漏", "内存溢出", "mem"],
            "scene_patterns": ["memory_alert", "oom"],
        },
        "diagnostic_steps": [
            {
                "step": 1,
                "action": "check_memory_trend",
                "description": "查看内存使用趋势是否持续增长",
            },
            {"step": 2, "action": "check_oom_killer", "description": "检查 OOM Killer 日志"},
            {"step": 3, "action": "heap_dump", "description": "分析 heap dump 定位泄漏对象"},
            {"step": 4, "action": "check_gc_logs", "description": "分析 GC 日志中 full GC 频率"},
        ],
        "recommended_tools": ["GetMetrics", "SearchLog", "GetProcessInfo", "GetMemoryUsage"],
        "evidence_requirements": ["memory_usage_mb", "memory_trend", "oom_events", "gc_frequency"],
        "risk_warnings": [
            "重启仅临时缓解，必须定位根因",
            "heap dump 分析可能导致服务短暂卡顿",
            "区分 native memory 和 JVM/interpreter memory",
        ],
        "report_template": (
            "## 内存泄漏诊断报告\n\n"
            "**现象**: {goal}\n\n"
            "**根因**: {root_cause}\n\n"
            "**证据**:\n{evidence}\n\n"
            "**建议**:\n{recommendations}\n"
        ),
    },
    {
        "skill_id": "sre-disk-full",
        "name": "Disk Full Diagnosis",
        "description": "Diagnose disk space exhaustion and identify space consumers.",
        "trigger_conditions": {
            "keywords": ["磁盘", "disk", "磁盘满", "磁盘空间", "no space", "disk full"],
            "scene_patterns": ["disk_alert", "storage"],
        },
        "diagnostic_steps": [
            {"step": 1, "action": "check_disk_usage", "description": "查看各挂载点磁盘使用率"},
            {"step": 2, "action": "find_large_files", "description": "查找大文件和目录"},
            {"step": 3, "action": "check_logs", "description": "检查日志文件是否无限增长"},
            {"step": 4, "action": "check_inodes", "description": "检查 inode 使用情况"},
        ],
        "recommended_tools": ["GetMetrics", "SearchLog", "GetDiskUsage"],
        "evidence_requirements": ["disk_usage_percent", "large_files", "inode_usage"],
        "risk_warnings": [
            "勿直接删除正在写入的日志文件",
            "优先清理临时文件和过期日志",
            "关注 inode 耗尽场景（大量小文件）",
        ],
        "report_template": (
            "## 磁盘满诊断报告\n\n"
            "**现象**: {goal}\n\n"
            "**根因**: {root_cause}\n\n"
            "**证据**:\n{evidence}\n\n"
            "**建议**:\n{recommendations}\n"
        ),
    },
    {
        "skill_id": "sre-slow-response",
        "name": "Slow Response Diagnosis",
        "description": "Diagnose slow API response times and latency spikes.",
        "trigger_conditions": {
            "keywords": ["慢", "slow", "延迟", "latency", "响应慢", "超时", "timeout"],
            "scene_patterns": ["latency_alert", "performance", "slow_api"],
        },
        "diagnostic_steps": [
            {
                "step": 1,
                "action": "check_latency_metrics",
                "description": "查看 P50/P95/P99 延迟分布",
            },
            {"step": 2, "action": "trace_requests", "description": "追踪慢请求链路"},
            {"step": 3, "action": "check_downstream", "description": "检查下游依赖响应时间"},
            {
                "step": 4,
                "action": "check_connection_pool",
                "description": "检查连接池状态和排队情况",
            },
        ],
        "recommended_tools": ["GetMetrics", "SearchLog", "GetTrace", "GetConnectionPool"],
        "evidence_requirements": ["latency_p99", "slow_request_count", "downstream_latency"],
        "risk_warnings": [
            "区分网络延迟和服务端延迟",
            "关注连接池耗尽导致的排队",
            "检查是否有全表查询或 N+1 问题",
        ],
        "report_template": (
            "## 响应慢诊断报告\n\n"
            "**现象**: {goal}\n\n"
            "**根因**: {root_cause}\n\n"
            "**证据**:\n{evidence}\n\n"
            "**建议**:\n{recommendations}\n"
        ),
    },
    {
        "skill_id": "sre-service-unavailable",
        "name": "Service Unavailable Diagnosis",
        "description": "Diagnose service downtime, 5xx errors, and health check failures.",
        "trigger_conditions": {
            "keywords": ["服务不可用", "unavailable", "5xx", "down", "宕机", "故障", "挂了"],
            "scene_patterns": ["service_down", "health_check_fail"],
        },
        "diagnostic_steps": [
            {"step": 1, "action": "check_health", "description": "检查服务健康检查状态"},
            {"step": 2, "action": "check_error_rate", "description": "查看 5xx 错误率趋势"},
            {"step": 3, "action": "check_restart", "description": "检查服务重启和 OOM 记录"},
            {
                "step": 4,
                "action": "check_dependencies",
                "description": "检查依赖服务（DB/Redis/MQ）是否正常",
            },
        ],
        "recommended_tools": ["GetMetrics", "SearchLog", "GetHealth", "GetServiceStatus"],
        "evidence_requirements": [
            "error_rate",
            "health_status",
            "restart_count",
            "dependency_status",
        ],
        "risk_warnings": [
            "先确认影响范围再决定是否回滚",
            "检查是否为瞬时抖动还是持续故障",
            "关注级联故障风险",
        ],
        "report_template": (
            "## 服务不可用诊断报告\n\n"
            "**现象**: {goal}\n\n"
            "**根因**: {root_cause}\n\n"
            "**证据**:\n{evidence}\n\n"
            "**建议**:\n{recommendations}\n"
        ),
    },
    {
        "skill_id": "sre-deploy-regression",
        "name": "Deploy Regression Diagnosis",
        "description": "Diagnose issues introduced by a recent deployment.",
        "trigger_conditions": {
            "keywords": ["部署", "deploy", "上线", "发版", "回归", "regression", "新版本"],
            "scene_patterns": ["deploy_regression", "post_deploy"],
        },
        "diagnostic_steps": [
            {
                "step": 1,
                "action": "check_deploy_timeline",
                "description": "确认问题出现时间与发布时间关系",
            },
            {
                "step": 2,
                "action": "compare_versions",
                "description": "对比变更版本的配置和代码差异",
            },
            {
                "step": 3,
                "action": "check_feature_flags",
                "description": "检查 Feature Flag 和灰度配置",
            },
            {"step": 4, "action": "rollback_assessment", "description": "评估是否需要回滚"},
        ],
        "recommended_tools": ["GetMetrics", "SearchLog", "GetDeployHistory", "GetConfigDiff"],
        "evidence_requirements": [
            "deploy_timestamp",
            "error_rate_before_after",
            "config_diff",
            "feature_flags",
        ],
        "risk_warnings": [
            "确认回滚是否安全（数据库迁移兼容性）",
            "检查是否有依赖变更的服务",
            "灰度回滚优于全量回滚",
        ],
        "report_template": (
            "## 部署回归诊断报告\n\n"
            "**现象**: {goal}\n\n"
            "**变更时间**: {deploy_time}\n\n"
            "**根因**: {root_cause}\n\n"
            "**证据**:\n{evidence}\n\n"
            "**建议**: {recommendations}\n"
        ),
    },
    {
        "skill_id": "sre-queue-backlog",
        "name": "Queue Backlog Diagnosis",
        "description": "Diagnose message queue backlog and consumer lag issues.",
        "trigger_conditions": {
            "keywords": ["队列", "queue", "积压", "backlog", "消费延迟", "consumer lag"],
            "scene_patterns": ["queue_alert", "consumer_lag"],
        },
        "diagnostic_steps": [
            {"step": 1, "action": "check_queue_depth", "description": "查看队列深度和增长趋势"},
            {"step": 2, "action": "check_consumers", "description": "检查消费者数量和消费速率"},
            {"step": 3, "action": "check_slow_messages", "description": "识别处理耗时的慢消息"},
            {"step": 4, "action": "check_dlq", "description": "检查死信队列中的异常消息"},
        ],
        "recommended_tools": ["GetMetrics", "SearchLog", "GetQueueStatus", "GetConsumerLag"],
        "evidence_requirements": ["queue_depth", "consumer_rate", "dlq_count", "message_age"],
        "risk_warnings": [
            "消费者扩容前先确认是否为消息处理异常",
            "避免盲目跳过积压消息导致数据丢失",
            "关注消息 TTL 过期风险",
        ],
        "report_template": (
            "## 消息队列积压诊断报告\n\n"
            "**现象**: {goal}\n\n"
            "**根因**: {root_cause}\n\n"
            "**证据**:\n{evidence}\n\n"
            "**建议**:\n{recommendations}\n"
        ),
    },
]


class SkillCatalog:
    """In-memory catalog of built-in and custom SRE skills.

    Usage::

        catalog = SkillCatalog()
        matched = catalog.match(scene={"tools": ["GetMetrics"]}, goal="CPU 高负载")
        # -> [SkillManifest(skill_id="sre-cpu-high", ...)]
    """

    def __init__(self, custom_skills: list[dict[str, Any]] | None = None) -> None:
        self._builtin = [SkillManifest(**s) for s in BUILTIN_SKILLS]
        self._custom = [SkillManifest(**s) for s in (custom_skills or [])]

    @property
    def all_skills(self) -> list[SkillManifest]:
        return list(self._builtin) + list(self._custom)

    def get(self, skill_id: str) -> SkillManifest | None:
        for skill in self.all_skills:
            if skill.skill_id == skill_id:
                return skill
        return None

    def match(self, *, scene: dict[str, Any], goal: str) -> list[SkillManifest]:
        """Match skills whose trigger conditions match the goal and scene."""
        goal_lower = goal.lower()
        matched: list[SkillManifest] = []
        for skill in self.all_skills:
            conditions = skill.trigger_conditions
            keywords = conditions.get("keywords", [])
            scene_patterns = conditions.get("scene_patterns", [])

            keyword_hit = any(kw.lower() in goal_lower for kw in keywords)
            scene_hit = any(
                sp in scene.get("scene_patterns", []) or sp in scene.get("name", "")
                for sp in scene_patterns
            )

            if keyword_hit or scene_hit:
                matched.append(skill)
        return matched
