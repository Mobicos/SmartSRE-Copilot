from __future__ import annotations

# ruff: noqa: E402,I001

import os
from pathlib import Path
import subprocess
import time
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.platform.compat import stabilize_windows_platform_detection

stabilize_windows_platform_detection()


def _load_dotenv_for_tests() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    allowed_keys = {
        "POSTGRES_DSN",
        "SMARTSRE_TEST_POSTGRES_DSN",
        "SMARTSRE_TEST_POSTGRES_HOST",
    }
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in allowed_keys:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv_for_tests()

import psycopg
import pytest
from alembic.config import Config as AlembicConfig
from psycopg import OperationalError
from sqlalchemy import text

from alembic import command
from app.api.providers import reset_container_for_testing
from app.config import config
from app.platform.persistence.database import get_engine
from app.platform.persistence.database import reset_for_testing
from app.platform.persistence.schema import REQUIRED_TABLES
from app.security.auth import load_api_key_roles

config.app_api_key = ""
config.api_keys_json = ""
load_api_key_roles.cache_clear()

_DEFAULT_BASE_DSN_TEMPLATE = "postgresql://smartsre:smartsre@{host}:5432/postgres"
_PG_CONTAINER_NAMES = (
    "smartsre-local-postgres",
    "smartsre-postgres",
    "smartsre-dev-postgres",
)
_TEST_DB_NAME = f"smartsre_test_{uuid.uuid4().hex[:8]}"
_PG_CONNECT_TIMEOUT_SECONDS = 30.0
_PG_HOST_PROBE_TIMEOUT_SECONDS = 4.0
_PG_CONNECT_RETRY_SECONDS = 0.5


def _postgres_host_candidates() -> list[str]:
    """Return PostgreSQL hosts in the order most reliable for local tests."""
    candidates: list[str] = []
    configured_hosts = [
        item.strip()
        for item in os.getenv("SMARTSRE_TEST_POSTGRES_HOST", "").split(",")
        if item.strip()
    ]
    candidates.extend(configured_hosts)

    for container_name in _PG_CONTAINER_NAMES:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        host = result.stdout.strip()
        if result.returncode == 0 and host:
            candidates.append(host)

    candidates.extend(["localhost", "127.0.0.1"])
    candidates.extend(_PG_CONTAINER_NAMES)
    return list(dict.fromkeys(candidates))


def _normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def _dsn_with_database(dsn: str, database_name: str) -> str:
    normalized = _normalize_psycopg_dsn(dsn)
    parts = urlsplit(normalized)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database_name}", parts.query, ""))


def _dsn_with_search_path(dsn: str, schema_name: str) -> str:
    normalized = _normalize_psycopg_dsn(dsn)
    parts = urlsplit(normalized)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema_name},public"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _configured_postgres_dsn() -> str | None:
    dsn = os.getenv("SMARTSRE_TEST_POSTGRES_DSN") or os.getenv("POSTGRES_DSN")
    return _normalize_psycopg_dsn(dsn.strip()) if dsn and dsn.strip() else None


def _explicit_test_postgres_dsn() -> str | None:
    dsn = os.getenv("SMARTSRE_TEST_POSTGRES_DSN")
    return _normalize_psycopg_dsn(dsn.strip()) if dsn and dsn.strip() else None


def _postgres_base_dsn_candidates() -> list[str]:
    candidates: list[str] = []
    configured_dsn = _configured_postgres_dsn()
    if configured_dsn:
        candidates.append(_dsn_with_database(configured_dsn, "postgres"))
    candidates.extend(
        _DEFAULT_BASE_DSN_TEMPLATE.format(host=host) for host in _postgres_host_candidates()
    )
    return list(dict.fromkeys(candidates))


def _connect_postgres_with_retry(
    dsn: str,
    *,
    timeout_seconds: float = _PG_CONNECT_TIMEOUT_SECONDS,
) -> psycopg.Connection:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            connect_timeout = max(min(int(timeout_seconds), 3), 1)
            return psycopg.connect(dsn, autocommit=True, connect_timeout=connect_timeout)
        except OperationalError as exc:
            last_error = exc
            time.sleep(_PG_CONNECT_RETRY_SECONDS)
    raise RuntimeError(f"PostgreSQL test database is not ready: {last_error}") from last_error


def _get_postgres_base_dsn() -> str:
    """Resolve a reachable PostgreSQL base DSN for cloud, Docker Desktop, Compose, or CI."""
    diagnostics: list[str] = []
    for base_dsn in _postgres_base_dsn_candidates():
        try:
            conn = _connect_postgres_with_retry(
                base_dsn,
                timeout_seconds=_PG_HOST_PROBE_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            safe_dsn = base_dsn.split("@", 1)[-1] if "@" in base_dsn else base_dsn
            diagnostics.append(f"{safe_dsn}: {type(exc).__name__}: {exc}")
            continue
        conn.close()
        return base_dsn

    joined_names = ", ".join(_PG_CONTAINER_NAMES)
    raise RuntimeError(
        "Unable to connect to PostgreSQL for tests. Set SMARTSRE_TEST_POSTGRES_DSN, "
        "POSTGRES_DSN, SMARTSRE_TEST_POSTGRES_HOST, publish Postgres on localhost:5432, "
        f"or start one of these containers: {joined_names}. "
        f"Attempts: {'; '.join(diagnostics)}"
    )


def _run_alembic_migrations(database_url: str) -> None:
    alembic_config = AlembicConfig("alembic.ini")
    original_dsn = os.environ.get("POSTGRES_DSN")
    os.environ["POSTGRES_DSN"] = database_url
    try:
        command.upgrade(alembic_config, "head")
    finally:
        if original_dsn is None:
            os.environ.pop("POSTGRES_DSN", None)
        else:
            os.environ["POSTGRES_DSN"] = original_dsn


@pytest.fixture(scope="session", autouse=True)
def _pg_base_dsn():
    """Resolve the PostgreSQL administrative database DSN."""
    return _get_postgres_base_dsn()


@pytest.fixture(scope="session", autouse=True)
def _create_test_database(_pg_base_dsn: str):
    """Create a dedicated test database for the session."""
    explicit_test_dsn = _explicit_test_postgres_dsn()
    if explicit_test_dsn:
        _run_alembic_migrations(explicit_test_dsn)
        yield explicit_test_dsn
        return

    base_dsn = _pg_base_dsn
    test_dsn = _dsn_with_database(base_dsn, _TEST_DB_NAME)
    conn = _connect_postgres_with_retry(base_dsn)
    try:
        conn.execute(f'CREATE DATABASE "{_TEST_DB_NAME}" TEMPLATE template0')
    except psycopg.errors.InsufficientPrivilege as exc:
        conn.close()
        configured_dsn = _configured_postgres_dsn()
        if not configured_dsn:
            raise RuntimeError(
                "PostgreSQL user cannot create temporary test databases. "
                "Grant CREATEDB to the configured user, or set SMARTSRE_TEST_POSTGRES_DSN "
                "to a dedicated disposable test database."
            ) from exc
        schema_name = _TEST_DB_NAME
        schema_dsn = _dsn_with_search_path(configured_dsn, schema_name)
        schema_conn = _connect_postgres_with_retry(configured_dsn)
        schema_conn.execute(f'CREATE SCHEMA "{schema_name}"')
        schema_conn.close()
        _run_alembic_migrations(schema_dsn)
        yield schema_dsn
        cleanup_conn = _connect_postgres_with_retry(configured_dsn)
        cleanup_conn.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        cleanup_conn.close()
        return
    else:
        conn.close()

    _run_alembic_migrations(test_dsn)

    yield test_dsn

    cleanup_conn = _connect_postgres_with_retry(base_dsn)
    cleanup_conn.execute(
        """
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = %s AND pid != pg_backend_pid()
        """,
        (_TEST_DB_NAME,),
    )
    cleanup_conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}"')
    cleanup_conn.close()


@pytest.fixture(autouse=True)
def isolated_postgres_database(_create_test_database: str):
    """Provide a clean PostgreSQL database for each test."""
    original_dsn = config.postgres_dsn
    original_api_key = config.app_api_key
    original_api_keys_json = config.api_keys_json

    config.postgres_dsn = _create_test_database
    config.app_api_key = ""
    config.api_keys_json = ""
    load_api_key_roles.cache_clear()

    reset_for_testing()
    reset_container_for_testing()

    yield

    # Truncate all tables
    engine = get_engine()
    with engine.begin() as connection:
        tables = ", ".join(REQUIRED_TABLES)
        connection.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))

    # Restore original config
    config.postgres_dsn = original_dsn
    config.app_api_key = original_api_key
    config.api_keys_json = original_api_keys_json
    reset_for_testing()
    reset_container_for_testing()
    load_api_key_roles.cache_clear()


@pytest.fixture(autouse=True)
def default_retry_policy():
    """Restore default retry configuration."""
    original = config.indexing_task_max_retries
    config.indexing_task_max_retries = 3
    yield
    config.indexing_task_max_retries = original
