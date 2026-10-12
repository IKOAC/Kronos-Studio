"""Only the 120B model is allowed; every bounded fallback attempt is metered."""

import json
import time
import pytest
from fastapi.encoders import jsonable_encoder
from schemas.groq_analysis import GROQ_MODEL, GroqAnalysisRequest
from schemas.trading_agents import TradingAgentsRequest
from services.ai_providers import ProviderAnalysisService, PROVIDERS
from services.ai_allowance import AllowanceReporter
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
        allowance_reporter=AllowanceReporter(transport=lambda url, key: (503, {})),
    )
    return service, tracker, calls, secrets


def request():
    return GroqAnalysisRequest.model_validate(input_json())


@pytest.mark.parametrize("target", range(3))
def test_each_provider_uses_only_exact_120b_id_and_reports_actual_provider(
    setup, target
):
    service, tracker, calls, secrets = setup
    for provider in PROVIDERS[:target]:
        (service.key_directory / (provider.name + "_key")).unlink()
    result = service.analyze(request())
    assert result["provider"] == PROVIDERS[target].name
    assert result["model"] == GROQ_MODEL
    assert calls[0][1]["model"] == PROVIDERS[target].model
    if target == 2:
        assert calls[0][1]["reasoning"] == {"effort": "high", "exclude": True}
        assert "reasoning_effort" not in calls[0][1]
    else:
        assert calls[0][1]["reasoning_effort"] == "high"
    assert not any(
        key in calls[0][1] for key in ("models", "route", "fallbacks", "preset")
    )
    journal = service.journal.log.read_text()
    assert not any(key in journal for key in secrets.values())
    assert not any(
        key in json.dumps(jsonable_encoder(result)) for key in secrets.values()
    )
    assert len(service.journal.rows()) == 1
    if target > 0:
        assert result["quota"].usage_percent is None
        assert result["quota"].token_limit_assumed is None


def test_quota_and_credit_exhaustion_falls_back_immediately_and_meters_all(
    setup, monkeypatch
):
    service, tracker, calls, secrets = setup
    monkeypatch.setattr(
        time, "sleep", lambda *args: pytest.fail("Fallback must not sleep")
    )
    original = service.provider_transport

    def transport(provider, payload, key):
        if provider.name != "openrouter":
            calls.append((provider.name, payload))
            return (
                (429 if provider.name == "groq" else 402),
                {},
                {"retry-after": "3600"},
            )
        return original(provider, payload, key)

    service.provider_transport = transport
    result = service.analyze(request())
    assert [c[0] for c in calls] == ["groq", "routeway", "openrouter"]
    assert result["provider"] == "openrouter"
    assert len(result["provider_attempts"]) == 3
    assert len(service.journal.rows()) == 3
    assert len(tracker.events) == 1
    # Persisted cooldown skips depleted providers on the next manual request.
    service.analyze(request())
    assert [c[0] for c in calls][-1] == "openrouter"
    assert len(calls) == 4


def test_groq_daily_reservation_skips_provider_before_sending(setup):
    service, tracker, calls, _ = setup
    tracker.tokens = 159999
    result = service.analyze(request())
    assert result["provider"] == "routeway"
    assert [c[0] for c in calls] == ["routeway"]
    assert tracker.events == []


def test_other_provider_known_daily_limits_are_enforced(setup):
    service, tracker, calls, _ = setup
    tracker.tokens = 159999
    path = service.key_directory / "provider_limits.json"
    path.write_text(json.dumps({"routeway": {"tokens": 1, "requests": 1}}))
    path.chmod(0o600)
    result = service.analyze(request())
    assert result["provider"] == "openrouter"
    assert [c[0] for c in calls] == ["openrouter"]


@pytest.mark.parametrize(
    "wrong", ["openai/gpt-oss-20b", "gpt-4", "openrouter/auto", None]
)
def test_wrong_or_missing_returned_model_never_reaches_analysis(setup, wrong):
    service, tracker, calls, _ = setup
    original = service.provider_transport

    def transport(provider, payload, key):
        status, body, headers = original(provider, payload, key)
        if provider.name == "groq":
            body["model"] = wrong
        return status, body, headers

    service.provider_transport = transport
    result = service.analyze(request())
    assert result["provider"] == "routeway"
    assert result["provider_attempts"][0]["status"] == "model_mismatch"
    assert len(service.journal.rows()) == 2


def test_client_or_internal_payload_cannot_select_other_model(setup):
    service, tracker, calls, _ = setup
    with pytest.raises(GroqAnalysisError):
        service.wire_payload(PROVIDERS[0], {"model": "openrouter/auto"})
    assert calls == []


def test_all_exhausted_providers_stop_after_one_attempt_each(setup):
    service, tracker, calls, _ = setup

    def fail(provider, payload, key):
        calls.append((provider.name, payload))
        return 429, {}, {}

    service.provider_transport = fail
    with pytest.raises(GroqAnalysisError) as exc:
        service.analyze(request())
    assert exc.value.code == "ALL_PROVIDERS_UNAVAILABLE"
    assert len(calls) == len(service.journal.rows()) == 3


def test_uncertain_transport_attempt_is_counted_before_fallback(setup):
    service, tracker, calls, _ = setup
    original = service.provider_transport

    def transport(provider, payload, key):
        if provider.name == "groq":
            calls.append((provider.name, payload))
            raise TimeoutError()
        return original(provider, payload, key)

    service.provider_transport = transport
    result = service.analyze(request())
    assert result["provider"] == "routeway"
    assert service.journal.rows()[0]["estimated"]
    assert tracker.events[0][3] == 0
    assert len(service.journal.rows()) == 2


def test_trading_agents_can_switch_provider_between_turns_without_changing_metrics(
    setup,
):
    service, tracker, calls, _ = setup
    original = service.provider_transport

    def transport(provider, payload, key):
        status, body, headers = original(provider, payload, key)
        if provider.name == "groq":
            headers["x-ratelimit-remaining-tokens"] = "0"
        return status, body, headers

    service.provider_transport = transport
    result = TradingAgentsService(service).analyze(
        TradingAgentsRequest.model_validate(input_json())
    )
    assert [c[0] for c in calls] == ["groq", "routeway", "routeway"]
    assert result["providers_used"] == ["groq", "routeway"]
    assert result["run_stats"].requests_used == 3
    assert len(result["agents"]) == 3


def test_provider_status_reporting_does_not_make_model_calls(setup):
    service, tracker, calls, secrets = setup
    status = service.statuses()
    assert calls == []
    assert len(status["providers"]) == 3
    assert not any(secret in json.dumps(status) for secret in secrets.values())


def test_reported_request_exhaustion_switches_before_next_research_turn(setup):
    service, tracker, calls, _ = setup
    original = service.provider_transport

    def transport(provider, payload, key):
        status, body, headers = original(provider, payload, key)
        if provider.name == "groq":
            headers["x-ratelimit-remaining-requests"] = "0"
        return status, body, headers

    service.provider_transport = transport
    result = TradingAgentsService(service).analyze(
        TradingAgentsRequest.model_validate(input_json())
    )
    assert [name for name, _ in calls] == ["groq", "routeway", "routeway"]
    assert result["run_stats"].requests_used == 3


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
