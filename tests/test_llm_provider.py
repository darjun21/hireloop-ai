"""
Provider/retry/fallback behavior tests (Part I). No real network calls —
everything is exercised against ScriptedProvider / MockLLMProvider.
"""

import logging

import pytest

from src.llm.base import LLMResult, RetryPolicy
from src.llm.client import LLMClient
from src.llm.errors import HireLoopLLMError, LLMErrorType
from src.llm.mock_provider import MockLLMProvider
from src.llm.schemas import ExtractedProfileData
from tests.fakes import ScriptedProvider

_FAST_RETRY = RetryPolicy(max_retries=2, base_delay_seconds=0.001, max_delay_seconds=0.002)


def test_primary_succeeds_on_first_attempt():
    primary = ScriptedProvider("primary", [lambda: "ok"])
    client = LLMClient(primary=primary, retry_policy=_FAST_RETRY)

    result = client.invoke("hi")

    assert result.text == "ok"
    assert result.attempts == 1
    assert result.used_fallback is False


def test_primary_times_out_once_then_succeeds():
    primary = ScriptedProvider("primary", [LLMErrorType.TIMEOUT, lambda: "ok"])
    client = LLMClient(primary=primary, retry_policy=_FAST_RETRY)

    result = client.invoke("hi")

    assert result.text == "ok"
    assert result.attempts == 2
    assert result.used_fallback is False


def test_primary_exhausts_retries_then_fallback_succeeds():
    primary = ScriptedProvider("primary", [LLMErrorType.TIMEOUT, LLMErrorType.TIMEOUT, LLMErrorType.TIMEOUT])
    fallback = ScriptedProvider("fallback", [lambda: "fallback-ok"])
    client = LLMClient(primary=primary, fallback=fallback, retry_policy=_FAST_RETRY)

    result = client.invoke("hi")

    assert result.text == "fallback-ok"
    assert result.used_fallback is True
    assert primary.call_count == 3  # 1 initial + 2 retries = max_retries + 1


def test_both_primary_and_fallback_fail():
    primary = ScriptedProvider("primary", [LLMErrorType.TIMEOUT] * 3)
    fallback = ScriptedProvider("fallback", [LLMErrorType.PROVIDER_UNAVAILABLE] * 3)
    client = LLMClient(primary=primary, fallback=fallback, retry_policy=_FAST_RETRY)

    with pytest.raises(HireLoopLLMError) as exc_info:
        client.invoke("hi")

    assert "primary" in str(exc_info.value)
    assert "fallback" in str(exc_info.value)


def test_authentication_error_does_not_endlessly_retry():
    primary = ScriptedProvider("primary", [LLMErrorType.AUTH_ERROR])
    client = LLMClient(primary=primary, retry_policy=_FAST_RETRY)

    with pytest.raises(HireLoopLLMError) as exc_info:
        client.invoke("hi")

    assert exc_info.value.error_type == LLMErrorType.AUTH_ERROR
    assert primary.call_count == 1  # not retryable -> exactly one attempt


def test_auth_error_falls_through_to_fallback_without_retrying_primary():
    primary = ScriptedProvider("primary", [LLMErrorType.AUTH_ERROR])
    fallback = ScriptedProvider("fallback", [lambda: "fallback-ok"])
    client = LLMClient(primary=primary, fallback=fallback, retry_policy=_FAST_RETRY)

    result = client.invoke("hi")

    assert result.text == "fallback-ok"
    assert primary.call_count == 1


def test_structured_response_malformed_raises_controlled_error():
    primary = ScriptedProvider("primary", [LLMErrorType.MALFORMED_RESPONSE])
    client = LLMClient(primary=primary, retry_policy=_FAST_RETRY)

    with pytest.raises(HireLoopLLMError) as exc_info:
        client.structured_output("hi", ExtractedProfileData)

    assert exc_info.value.error_type == LLMErrorType.MALFORMED_RESPONSE
    assert primary.call_count == 1  # malformed response is not retried


def test_mock_provider_works_without_api_keys():
    provider = MockLLMProvider()
    client = LLMClient(primary=provider, retry_policy=_FAST_RETRY)

    result = client.invoke("no api key needed")

    assert result.provider == "mock"
    assert provider.health_check() is True


def test_secrets_do_not_appear_in_error_messages():
    secret = "sk-super-secret-key-do-not-leak"
    primary = ScriptedProvider("primary", [LLMErrorType.AUTH_ERROR])
    client = LLMClient(primary=primary, retry_policy=_FAST_RETRY)

    with pytest.raises(HireLoopLLMError) as exc_info:
        client.invoke(secret)

    assert secret not in str(exc_info.value)
    assert secret not in repr(exc_info.value)


def test_secrets_do_not_appear_in_logs(caplog):
    secret = "sk-super-secret-key-do-not-leak"
    primary = ScriptedProvider("primary", [LLMErrorType.TIMEOUT, lambda: "ok"])
    client = LLMClient(primary=primary, retry_policy=_FAST_RETRY)

    with caplog.at_level(logging.WARNING, logger="hireloop.llm"):
        client.invoke(secret)

    for record in caplog.records:
        assert secret not in record.getMessage()


def test_retry_delay_grows_but_stays_bounded():
    policy = RetryPolicy(max_retries=5, base_delay_seconds=1.0, max_delay_seconds=3.0)
    assert policy.delay_for_attempt(1) == 1.0
    assert policy.delay_for_attempt(2) == 2.0
    assert policy.delay_for_attempt(3) == 3.0  # would be 4.0 uncapped
    assert policy.delay_for_attempt(10) == 3.0


def test_retries_are_bounded_not_infinite():
    # Script has exactly max_retries+1 failures available; a fourth call
    # would raise AssertionError from the script itself if reached.
    primary = ScriptedProvider("primary", [LLMErrorType.TIMEOUT, LLMErrorType.TIMEOUT, LLMErrorType.TIMEOUT])
    client = LLMClient(primary=primary, retry_policy=RetryPolicy(max_retries=2, base_delay_seconds=0.001))

    with pytest.raises(HireLoopLLMError):
        client.invoke("hi")

    assert primary.call_count == 3
