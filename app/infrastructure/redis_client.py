"""Redis 基础设施封装。"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from app.config import config

try:
    from redis import Redis
    from redis.exceptions import RedisError
except Exception:  # pragma: no cover - 运行环境可能未安装 redis
    Redis = None

    class RedisError(Exception):
        """Redis 占位异常。"""


class RedisManager:
    """管理 Redis 连接与任务队列操作。"""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._client: Redis | None = None

    @property
    def is_initialized(self) -> bool:
        return self._client is not None

    def initialize(self) -> None:
        if self._client is not None:
            return
        if Redis is None:
            raise RuntimeError("当前配置需要 Redis，但未安装 redis 包")

        self._client = Redis.from_url(self.redis_url, decode_responses=True)
        self._client.ping()
        logger.info(f"Redis 初始化完成: {self.redis_url}")

    def health_check(self) -> bool:
        try:
            self.initialize()
            assert self._client is not None
            return bool(self._client.ping())
        except Exception as exc:
            logger.error(f"Redis 健康检查失败: {exc}")
            return False

    def enqueue_json(self, queue_name: str, payload: dict[str, Any]) -> None:
        self.initialize()
        assert self._client is not None
        self._client.rpush(queue_name, json.dumps(payload, ensure_ascii=False))

    def dequeue_json(self, queue_name: str, timeout_seconds: int) -> dict[str, Any] | None:
        self.initialize()
        assert self._client is not None
        result = self._client.blpop(queue_name, timeout=timeout_seconds)
        if result is None:
            return None

        _, raw_payload = result
        return json.loads(raw_payload)


redis_manager = RedisManager(config.redis_url)
