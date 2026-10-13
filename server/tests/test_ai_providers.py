"""Only the 120B model is allowed; every bounded fallback attempt is metered."""

import json
import time
import pytest
from fastapi.encoders import jsonable_encoder
from schemas.groq_analysis import GROQ_MODEL, GroqAnalysisRequest
from schemas.trading_agents import TradingAgentsRequest
from services.ai_providers import ProviderAnalysisService, PROVIDERS
from services.groq_analysis import GroqAnalysisError
from services.trading_agents import TradingAgentsService
from test_groq_analysis import MockTracker, input_json, valid_response


@pytest.fixture
def setup(tmp_path, monkeypatch):
    keys = tmp_path / "keys"
    keys.mkdir(mode=0o700)
    secrets = {}
    for provider in PROVIDERS:
        monkeypatch.delenv(provider.env, raising=False)
        key = provider.name + "_private_test_token_" * 3
        secrets[provider.name] = key
        path = keys / (provider.name + "_key")
        path.write_text(key)
        path.chmod(0o600)
    calls = []
    tracker = MockTracker()

    def transport(provider, payload, key):
        assert key == secrets[provider.name]
        calls.append((provider.name, payload))
        status, body, headers = valid_response()
        body["model"] = provider.model
        return status, body, headers

    service = ProviderAnalysisService(
        key_directory=keys,
        journal_root=tmp_path / "journal",
        provider_transport=transport,
        groq_tracker=tracker,
        lock_path=tmp_path / "usage.lock",
    )
    return service, tracker, calls, secrets


def request():
    return GroqAnalysisRequest.model_validate(input_json())


def test_optional_forecast_prompt_uses_only_applicable_limitations(setup):
    from services.financial_analysis.engine import analyze_financials
    from schemas.financial_analysis import FinancialAnalysisResponse

    service, _, _, _ = setup
    body = input_json()
    body["forecasts"] = []
    snapshot = GroqAnalysisRequest.model_validate(body)
    payload, facts, _ = service._make_prompt(
        FinancialAnalysisResponse.model_validate(analyze_financials(snapshot)),
        snapshot.symbol,
        snapshot.interval,
    )
    limits = payload["response_format"]["json_schema"]["schema"]["properties"][
        "limitations"
    ]["items"]["enum"]
    assert not any("forecast" in value.lower() for value in limits)
    assert not any(key.startswith("forecast.") for key in facts)


def test_groq_json_generation_failure_recovers_once_and_meters_both_attempts(setup):
    service, tracker, calls, _ = setup
    original = service.provider_transport

    def transport(provider, payload, key):
        if not calls:
            calls.append((provider.name, payload))
            return 400, {"error": {"code": "output_invalid"}}, {}
        return original(provider, payload, key)

    service.provider_transport = transport
    result = service.analyze(request())
    assert result["provider"] == "groq"
    assert [name for name, _ in calls] == ["groq", "groq"]
    assert calls[0][1]["response_format"]["type"] == "json_schema"
    assert calls[1][1]["response_format"] == {"type": "json_object"}
    assert calls[1][1]["reasoning_format"] == "hidden"
    assert service.journal.rows()[0]["estimated"]
    assert service.journal.rows()[0]["tokens"] > 0
    assert len(tracker.events) == 2
    assert service.journal.blocked("groq") is None


def test_repeated_json_generation_failure_is_bounded_and_does_not_cool_down_groq(setup):
    service, tracker, calls, _ = setup
    for provider in PROVIDERS[1:]:
        (service.key_directory / (provider.name + "_key")).unlink()

    def transport(provider, payload, key):
        calls.append((provider.name, payload))
        return 400, {"error": {"code": "output_invalid"}}, {}

    service.provider_transport = transport
    with pytest.raises(GroqAnalysisError) as caught:
        service.analyze(request())
    assert caught.value.code == "GROQ_INVALID_OUTPUT"
    assert len(calls) == 2
    assert len(tracker.events) == 2
    assert service.journal.blocked("groq") is None


def test_only_groq_is_active_and_status_never_generates(setup):
    service, _, calls, secrets = setup
    status = service.statuses()
    assert status["fallback_order"] == ["groq"]
    assert [p["provider"] for p in status["providers"]] == ["groq"]
    assert calls == []
    assert not any(secret in json.dumps(status) for secret in secrets.values())
    result = service.analyze(request())
    assert result["provider"] == "groq"
    assert result["model"] == GROQ_MODEL
    assert [name for name, _ in calls] == ["groq"]
    assert len(service.journal.rows()) == 1


def test_daily_preflight_returns_daily_cap_instead_of_generic_unavailable(setup):
    service, tracker, calls, _ = setup
    tracker.tokens = 159999
    with pytest.raises(GroqAnalysisError) as caught:
        service.analyze(request())
    assert caught.value.code == "GROQ_DAILY_CAP"
    assert calls == []


def test_missing_key_does_not_attempt_another_provider(setup):
    service, _, calls, _ = setup
    (service.key_directory / "groq_key").unlink()
    with pytest.raises(GroqAnalysisError):
        service.analyze(request())
    assert calls == []


@pytest.mark.parametrize("wrong", ["openai/gpt-oss-20b", "gpt-4", None])
def test_wrong_model_is_metered_but_never_accepted(setup, wrong):
    service, _, calls, _ = setup
    original = service.provider_transport

    def transport(provider, payload, key):
        status, body, headers = original(provider, payload, key)
        body["model"] = wrong
        return status, body, headers

    service.provider_transport = transport
    with pytest.raises(GroqAnalysisError):
        service.analyze(request())
    assert len(calls) == 1
    assert service.journal.blocked("groq")["reason"] == "model_mismatch"


def test_rate_limit_failure_and_cooldown_return_specific_error(setup):
    service, _, calls, _ = setup

    def transport(provider, payload, key):
        calls.append((provider.name, payload))
        return 429, {}, {"retry-after": "60"}

    service.provider_transport = transport
    for _ in range(2):
        with pytest.raises(GroqAnalysisError) as caught:
            service.analyze(request())
        assert caught.value.code == "GROQ_RATE_LIMITED"
    assert len(calls) == 1


def test_minute_tokens_refill_between_all_three_research_turns(setup, monkeypatch):
    service, _, calls, _ = setup
    sleeps = []
    monkeypatch.setattr("services.groq_analysis.time.sleep", sleeps.append)
    original = service.provider_transport

    def transport(provider, payload, key):
        status, body, _ = original(provider, payload, key)
        return (
            status,
            body,
            {
                "x-ratelimit-limit-tokens": "12000",
                "x-ratelimit-remaining-tokens": "1000",
                "x-ratelimit-reset-tokens": "20s",
            },
        )

    service.provider_transport = transport
    result = TradingAgentsService(service).analyze(
        TradingAgentsRequest.model_validate(input_json())
    )
    assert len(result["agents"]) == 3
    assert [name for name, _ in calls] == ["groq"] * 3
    assert len(sleeps) == 2
    assert all(0 < delay <= 45 for delay in sleeps)


def test_excessive_refill_wait_returns_rate_limit_without_generic_failure(setup):
    service, _, calls, _ = setup
    original = service.provider_transport

    def transport(provider, payload, key):
        status, body, _ = original(provider, payload, key)
        return (
            status,
            body,
            {
                "x-ratelimit-limit-tokens": "8000",
                "x-ratelimit-remaining-tokens": "0",
                "x-ratelimit-reset-tokens": "10m",
            },
        )

    service.provider_transport = transport
    with pytest.raises(GroqAnalysisError) as caught:
        TradingAgentsService(service).analyze(
            TradingAgentsRequest.model_validate(input_json())
        )
    assert caught.value.code == "GROQ_RATE_LIMITED"
    assert len(calls) == 1
    assert service.statuses()["providers"][0]["status"] == "ready"


def test_format_recovery_rechecks_quota_before_sending(setup):
    service, tracker, calls, _ = setup

    def transport(provider, payload, key):
        calls.append((provider.name, payload))
        tracker.tokens = 159000
        return 400, {"error": {"code": "output_invalid"}}, {}

    service.provider_transport = transport
    with pytest.raises(GroqAnalysisError) as caught:
        service.analyze(request())
    assert caught.value.code == "GROQ_DAILY_CAP"
    assert len(calls) == 1


def test_transport_failure_is_metered_and_keeps_specific_error(setup):
    service, _, calls, _ = setup

    def transport(provider, payload, key):
        calls.append((provider.name, payload))
        raise TimeoutError()

    service.provider_transport = transport
    with pytest.raises(GroqAnalysisError) as caught:
        service.analyze(request())
    assert caught.value.code == "GROQ_TRANSPORT_ERROR"
    assert len(calls) == 1
    assert service.journal.rows()[0]["estimated"]
    assert service.statuses()["providers"][0]["failure_reason"] == "transport_error"


def test_transient_gateway_error_retries_once_without_marking_provider_unavailable(
    setup, monkeypatch
):
    service, _, calls, _ = setup
    sleeps = []
    monkeypatch.setattr("services.ai_providers.time.sleep", sleeps.append)
    original = service.provider_transport

    def transport(provider, payload, key):
        if not calls:
            calls.append((provider.name, payload))
            return 503, {}, {}
        return original(provider, payload, key)

    service.provider_transport = transport
    result = service.analyze(request())
    assert result["provider"] == "groq"
    assert len(calls) == 2
    assert sleeps == [1]
    assert service.journal.blocked("groq") is None


def test_gateway_and_json_failure_share_one_retry_budget(setup, monkeypatch):
    service, _, calls, _ = setup
    monkeypatch.setattr("services.ai_providers.time.sleep", lambda _: None)

    def transport(provider, payload, key):
        calls.append((provider.name, payload))
        if len(calls) == 1:
            return 503, {}, {}
        return 400, {"error": {"code": "output_invalid"}}, {}

    service.provider_transport = transport
    with pytest.raises(GroqAnalysisError) as caught:
        service.analyze(request())
    assert caught.value.code == "GROQ_INVALID_OUTPUT"
    assert len(calls) == 2
