from __future__ import annotations

from app.infrastructure.knowledge.vector_store_manager import _milvus_string_literal
from app.security.auth import _api_key_subject
from app.security.rate_limit import RateLimiter, RateLimitPolicy


def test_milvus_string_literal_escapes_injected_expression_parts():
    payload = 'foo" || metadata["tenant"] != "prod\\bar\nnext'

    literal = _milvus_string_literal(payload)

    assert literal == '"foo\\" || metadata[\\"tenant\\"] != \\"prod\\\\bar\\nnext"'
    assert literal.startswith('"')
    assert literal.endswith('"')


def test_rate_limiter_isolates_keys_and_enforces_burst():
    limiter = RateLimiter()
    policy = RateLimitPolicy(requests_per_minute=1, burst=2)

    assert limiter.allow("stream:principal:a", policy) is True
    assert limiter.allow("stream:principal:a", policy) is True
    assert limiter.allow("stream:principal:a", policy) is False
    assert limiter.allow("stream:principal:b", policy) is True


def test_api_key_subject_is_stable_hash_not_key_prefix():
    subject = _api_key_subject("secret-api-key-value")

    assert subject.startswith("key:")
    assert "secret-api" not in subject
    assert subject == _api_key_subject("secret-api-key-value")
