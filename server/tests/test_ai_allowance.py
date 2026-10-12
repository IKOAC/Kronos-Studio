"""Read-only allowance reporting is cached, sanitized and isolated from generation."""

from concurrent.futures import ThreadPoolExecutor
import json
import math
import pytest
from fastapi.testclient import TestClient
from main import app
from routers.ai_market import _providers
from services.ai_allowance import AllowanceReporter, send_allowance
from test_ai_providers import setup as provider_setup, request


def test_openrouter_reports_real_credits_and_key_limit_separately():
    calls = []

    def transport(url, key):
        calls.append((url, key))
        return (
            (200, {"data": {"total_credits": 20, "total_usage": 3}})
            if url.endswith("credits")
            else (
                200,
                {
                    "data": {
                        "label": "private label",
                        "organization_id": "private id",
                        "limit": 10,
                        "usage": 2,
                        "limit_remaining": 8,
                        "limit_reset": "monthly",
                        "usage_daily": 0.5,
                        "free_model_daily_requests": {"remaining": 50},
                    }
                },
            )
        )

    reporter = AllowanceReporter(transport)
    result = reporter.report("openrouter", "private_inference_secret")
    assert result["balance_remaining_usd"] == 17
    assert result["spending_limit_usd"] == 10
    assert result["spending_remaining_usd"] == 8
    assert result["spending_percent"] == 20
    assert result["key_usage_daily_usd"] == 0.5
    assert result["status"] == "available"
    assert "private" not in json.dumps(result)
    assert "free_model" not in json.dumps(result)  # this is not the OSS-120B budget
    assert len(calls) == 2


def test_routeway_uses_separate_management_key_for_balance():
    calls = []
    reporter = AllowanceReporter(
        lambda url, key: (
            calls.append((url, key))
            or (200, {"balance": 4.25, "secret": "must not leave backend"})
        )
    )
    result = reporter.report("routeway", "inference_secret", "management_secret")
    assert result["balance_remaining_usd"] == 4.25
    assert result["spending_limit_usd"] is None
    assert calls == [
        ("https://api.routeway.ai/v1/account/balance", "management_secret")
    ]
    assert "secret" not in json.dumps(result)
    assert "inference_secret" not in repr(reporter._cache)
    assert "management_secret" not in repr(reporter._cache)


def test_openrouter_management_key_is_not_sent_to_key_usage_endpoint():
    calls = []

    def transport(url, key):
        calls.append((url, key))
        return (
            (200, {"data": {"limit": None, "usage": 0}})
            if url.endswith("/key")
            else (200, {"data": {"total_credits": 0, "total_usage": 0}})
        )

    reporter = AllowanceReporter(transport)
    result = reporter.report("openrouter", "inference_secret", "management_secret")
    assert [key for _, key in calls] == ["inference_secret", "management_secret"]
    assert result["balance_remaining_usd"] == 0
    assert (
        result["spending_limit_usd"] is None
    )  # no spending cap does not imply funded account


def test_tighter_effective_budget_is_reported_instead_of_larger_key_cap():
    reporter = AllowanceReporter(
        lambda url, key: (
            (200, {"data": {"total_credits": 50, "total_usage": 1}})
            if url.endswith("credits")
            else (
                200,
                {
                    "data": {
                        "limit": 20,
                        "usage": 3,
                        "limit_remaining": 17,
                        "effective_budget": {
                            "limit_usd": 5,
                            "spend_usd": 4,
                            "remaining_usd": 1,
                            "reset_interval": "weekly",
                            "guardrail_id": "private",
                        },
                    }
                },
            )
        )
    )
    result = reporter.report("openrouter", "key")
    assert result["spending_scope"] == "effective"
    assert result["spending_remaining_usd"] == 1
    assert result["spending_percent"] == 80
    assert result["limit_reset"] == "weekly"
    assert "guardrail" not in json.dumps(result)


@pytest.mark.parametrize("status", [401, 403])
def test_missing_balance_permission_is_explicit_and_does_not_erase_key_usage(status):
    reporter = AllowanceReporter(
        lambda url, key: (
            (status, {"error": "private response"})
            if url.endswith("credits")
            else (200, {"data": {"usage": 2, "limit": None}})
        )
    )
    result = reporter.report("openrouter", "key")
    assert result["status"] == "partial"
    assert result["balance_status"] == "permission_required"
    assert result["balance_remaining_usd"] is None
    assert result["spending_used_usd"] == 2
    assert "private response" not in json.dumps(result)


@pytest.mark.parametrize("value", [True, -1, "12", math.inf, math.nan, None])
def test_invalid_external_balance_is_not_reported_as_an_allowance(value):
    reporter = AllowanceReporter(lambda url, key: (200, {"balance": value}))
    result = reporter.report("routeway", "key")
    assert result["balance_remaining_usd"] is None
    assert result["status"] == "unavailable"


def test_timeout_and_malformed_response_are_safe_reporting_failures():
    def transport(*a):
        raise TimeoutError("private details")

    assert (
        AllowanceReporter(transport).report("routeway", "key")["status"]
        == "unavailable"
    )
    assert (
        AllowanceReporter(lambda *a: (200, [])).report("openrouter", "key")["status"]
        == "unavailable"
    )


def test_cache_deduplicates_concurrent_requests_and_expires():
    now = [0]
    calls = []
    reporter = AllowanceReporter(
        lambda url, key: (calls.append(1) or (200, {"balance": 5})),
        clock=lambda: now[0],
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: reporter.report("routeway", "key", "management"), range(8)
            )
        )
    assert len(calls) == 1
    results[0]["balance_remaining_usd"] = 0
    assert reporter.peek("routeway", "key", "management")["balance_remaining_usd"] == 5
    now[0] = 61
    assert reporter.peek("routeway", "key", "management") is None
    reporter.report("routeway", "key", "management")
    assert len(calls) == 2
    reporter.report("routeway", "key", "rotated_management")
    assert len(calls) == 3
    reporter.invalidate("routeway")
    assert reporter.peek("routeway", "key", "rotated_management") is None


def test_cached_zero_balance_skips_provider_without_more_network_reads(provider_setup):
    service, tracker, calls, _ = provider_setup
    reporting_calls = []

    def transport(url, key):
        reporting_calls.append(url)
        if "routeway" in url:
            return 200, {"balance": 0}
        if url.endswith("credits"):
            return 200, {"data": {"total_credits": 10, "total_usage": 0}}
        return 200, {"data": {"usage": 0, "limit": None}}

    service.allowance_reporter = AllowanceReporter(transport)
    statuses = service.statuses()
    assert statuses["providers"][1]["status"] == "quota_exhausted"
    tracker.tokens = 159999
    result = service.analyze(request())
    assert result["provider"] == "openrouter"
    assert [name for name, _ in calls] == ["openrouter"]
    assert len(reporting_calls) == 3  # inference uses cache only


def test_reporting_failure_does_not_break_inference_or_send_management_key(
    provider_setup,
):
    service, tracker, calls, _ = provider_setup
    secret = "management_only_private_secret"
    path = service.key_directory / "routeway_management_key"
    path.write_text(secret)
    path.chmod(0o600)
    service.statuses()
    tracker.tokens = 159999
    result = service.analyze(request())
    assert result["provider"] == "routeway"
    assert "management" not in json.dumps(calls)
    path.chmod(0o644)
    assert service.management_key("routeway") is None


def test_remote_clients_cannot_read_allowance_metadata(provider_setup):
    service, *_ = provider_setup
    app.dependency_overrides[_providers] = lambda: service
    try:
        with TestClient(app, client=("192.168.1.2", 54321)) as client:
            result = client.get("/api/analysis/providers")
        assert result.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_allowance_transport_cannot_be_redirected_to_arbitrary_host():
    with pytest.raises(ValueError):
        send_allowance("https://untrusted.example/secret", "key")
