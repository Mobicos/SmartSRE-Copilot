"""Query rewriter — expand user goal into multiple retrieval queries."""

from __future__ import annotations

import re

_CHINESE_SRE_ALIASES: dict[str, list[str]] = {
    "慢": ["slow_response", "latency"],
    "卡顿": ["slow_response", "latency"],
    "超时": ["timeout", "slow_response"],
    "宕机": ["service_unavailable", "down"],
    "挂了": ["service_unavailable", "down"],
    "故障": ["service_unavailable", "incident"],
    "cpu高": ["cpu_high", "cpu"],
    "cpu高负载": ["cpu_high", "load_average"],
    "内存泄漏": ["memory_leak", "oom"],
    "内存溢出": ["memory_leak", "oom"],
    "磁盘满": ["disk_full", "no_space"],
    "磁盘空间": ["disk_full"],
    "队列积压": ["queue_backlog", "consumer_lag"],
    "部署回归": ["deploy_regression", "regression"],
    "发版": ["deploy", "release"],
}


class QueryRewriter:
    """Expand a user goal string into multiple retrieval query variants.

    Heuristic-based (no LLM call). Returns 2–4 variants for broader recall::

        rewriter = QueryRewriter()
        variants = rewriter.rewrite("CPU 使用率过高，负载 95%")
        # -> ["CPU 使用率过高，负载 95%", "cpu_high load_average", ...]
    """

    def rewrite(self, goal: str, *, scene: dict | None = None) -> list[str]:
        """Return 2–4 query variants derived from the goal."""
        variants: list[str] = [goal]

        # Extract keyword aliases
        aliases = self._extract_aliases(goal)
        if aliases:
            variants.append(" ".join(aliases))

        # Append scene context if available
        if scene:
            scene_desc = scene.get("description", "") or scene.get("name", "")
            if scene_desc and scene_desc != goal:
                combined = f"{goal} {scene_desc}"
                if combined not in variants:
                    variants.append(combined)

        # Extract English keywords if goal is primarily Chinese
        en_keywords = self._extract_english_tokens(goal)
        if en_keywords:
            joined = " ".join(en_keywords)
            if joined not in variants:
                variants.append(joined)

        return variants[:4]

    def _extract_aliases(self, goal: str) -> list[str]:
        goal_lower = goal.lower()
        found: list[str] = []
        for pattern, aliases in _CHINESE_SRE_ALIASES.items():
            if pattern in goal_lower:
                found.extend(a for a in aliases if a not in found)
        return found

    def _extract_english_tokens(self, goal: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z_]{2,}", goal)
        return list(dict.fromkeys(tokens))  # dedupe, preserve order
