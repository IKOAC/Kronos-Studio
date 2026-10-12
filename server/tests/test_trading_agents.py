"""Exercise upstream debate nodes with fake metered transport; no live tokens."""

from concurrent.futures import ThreadPoolExecutor
import copy
import threading
import time

import pytest
from fastapi.testclient import TestClient
from main import app
from routers.trading_agents import _service
from schemas.trading_agents import TradingAgentsRequest, TradingAgentsResponse
from services.financial_analysis.engine import analyze_financials
from services.groq_analysis import GroqAnalysisError, GroqAnalysisService
from services.trading_agents import TradingAgentsService, RUN_RESERVATION
from test_groq_analysis import MockTracker, input_json, valid_response
from vendor.tradingagents import UPSTREAM_REVISION


@pytest.fixture
def setup(tmp_path):
    tmp_path.chmod(0o700)
    key = tmp_path / "key"
    key.write_text("gsk_" + "x" * 40)
    key.chmod(0o600)
    tracker = MockTracker()
    payloads = []

    def transport(payload, key):
        payloads.append(payload)
        return valid_response()

    groq = GroqAnalysisService(
        tracker=tracker,
        transport=transport,
        key_path=key,
        lock_path=tmp_path / "quota.lock",
    )
    service = TradingAgentsService(groq)
    return service, tracker, payloads


def client(service, host="127.0.0.1"):
    app.dependency_overrides[_service] = lambda: service
    return TestClient(app, client=(host, 54321))


@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides.clear()


def test_three_upstream_roles_share_metering_and_immutable_python_metrics(setup):
    service, tracker, payloads = setup
    body = input_json()
    original = copy.deepcopy(body)
    with client(service) as c:
        response = c.post(
            "/api/analysis/trading-agents",
            json=body,
            headers={"Origin": "http://localhost:3000"},
        )
    assert response.status_code == 200, response.text
    result = TradingAgentsResponse.model_validate(response.json())
    assert [a.role for a in result.agents] == ["bull", "bear", "research_manager"]
    assert result.metrics.model_dump() == analyze_financials(
        TradingAgentsRequest.model_validate(body)
    )
    assert body == original
    assert len(payloads) == len(tracker.events) == result.run_stats.requests_used == 3
    assert result.run_stats.tokens_used == 3120
    assert result.run_stats.reserved_tokens == RUN_RESERVATION
    assert result.run_stats.upstream_revision == UPSTREAM_REVISION
    assert "Bull Analyst" in payloads[1]["messages"][1]["content"]
    assert "Bear Analyst" in payloads[2]["messages"][1]["content"]
    assert "gsk_" not in response.text


@pytest.mark.parametrize("tokens,requests", [(150000, 0), (0, 798)])
def test_full_run_reserved_before_first_provider_call(setup, tokens, requests):
    service, tracker, payloads = setup
    tracker.tokens, tracker.requests = tokens, requests
    with client(service) as c:
        r = c.post("/api/analysis/trading-agents", json=input_json())
    assert r.status_code == 429
    assert payloads == tracker.events == []


@pytest.mark.parametrize(
    "host,origin",
    [
        ("192.168.1.1", "http://localhost:3000"),
        ("127.0.0.1", "https://evil.test"),
        ("127.0.0.1", "null"),
    ],
)
def test_local_guard_applies_to_agent_route(setup, host, origin):
    service, tracker, payloads = setup
    with client(service, host) as c:
        r = c.post(
            "/api/analysis/trading-agents",
            json=input_json(),
            headers={"Origin": origin},
        )
    assert r.status_code == 403
    assert payloads == []


@pytest.mark.parametrize("field", ["prompt", "max_rounds", "tools"])
def test_client_cannot_inject_unbounded_workflow(setup, field):
    service, tracker, payloads = setup
    with client(service) as c:
        r = c.post(
            "/api/analysis/trading-agents", json={**input_json(), field: "arbitrary"}
        )
    assert r.status_code == 422
    assert payloads == []


@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_invalid_evidence_stops_run_after_metering_without_retry(setup, fail_at):
    service, tracker, payloads = setup

    def transport(payload, key):
        payloads.append(payload)
        if len(payloads) == fail_at:
            return valid_response(
                findings={
                    "summary": "Uncertain outlook.",
                    "supporting_evidence_ids": ["fabricated.evidence"],
                    "conflicting_evidence_ids": [],
                    "limitations": [],
                }
            )
        return valid_response()

    service.groq.transport = transport
    with client(service) as c:
        r = c.post("/api/analysis/trading-agents", json=input_json())
    assert r.status_code == 502
    assert len(payloads) == len(tracker.events) == fail_at
    assert tracker.tokens == 1040 * fail_at


def test_provider_lower_daily_limit_stops_later_turn(setup):
    service, tracker, payloads = setup

    def transport(payload, key):
        payloads.append(payload)
        tracker.requests_limit = 2
        return valid_response()

    service.groq.transport = transport
    with client(service) as c:
        r = c.post("/api/analysis/trading-agents", json=input_json())
    assert r.status_code == 429
    assert len(payloads) == 1


def test_provider_minute_headers_pace_next_turn_without_extra_calls(setup, monkeypatch):
    service, tracker, payloads = setup
    sleeps = []
    monkeypatch.setattr("services.groq_analysis.time.sleep", sleeps.append)

    def transport(payload, key):
        payloads.append(payload)
        status, body, headers = valid_response()
        if len(payloads) < 3:
            headers.update(
                {
                    "x-ratelimit-limit-tokens": "8000",
                    "x-ratelimit-remaining-tokens": "0",
                    "x-ratelimit-reset-tokens": "1s",
                }
            )
        return status, body, headers

    service.groq.transport = transport
    service.analyze(TradingAgentsRequest.model_validate(input_json()))
    assert len(sleeps) == 2
    assert all(0 < delay <= 1 for delay in sleeps)
    assert len(payloads) == 3


def test_concurrent_runs_cannot_race_through_daily_reservation(setup):
    service, tracker, payloads = setup
    tracker.requests = 797

    def transport(payload, key):
        payloads.append(threading.current_thread().name)
        time.sleep(0.01)
        return valid_response()

    service.groq.transport = transport
    request = TradingAgentsRequest.model_validate(input_json())

    def run():
        try:
            return service.analyze(request)["run_stats"].requests_used
        except GroqAnalysisError as e:
            return e.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(results) == [3, 429]
    assert len(payloads) == 3
    assert len(set(payloads)) == 1


def test_snapshot_changes_when_final_forecast_changes(setup):
    service, tracker, payloads = setup
    body = input_json()
    first = service.analyze(TradingAgentsRequest.model_validate(body))["snapshot_id"]
    body["forecasts"][0]["final_close"] += 1
    second = service.analyze(TradingAgentsRequest.model_validate(body))["snapshot_id"]
    assert first != second


def test_generation_schema_limits_evidence_and_narrative_before_provider_call(setup):
    service, tracker, payloads = setup
    service.analyze(TradingAgentsRequest.model_validate(input_json()))
    for payload in payloads:
        properties = payload["response_format"]["json_schema"]["schema"]["properties"]
        assert "No digits" in properties["summary"]["description"]
        assert "pattern" not in properties["summary"]
        assert (
            "technical.rsi_14" in properties["supporting_evidence_ids"]["items"]["enum"]
        )
        assert (
            "Forecast agreement does not establish accuracy."
            in properties["limitations"]["items"]["enum"]
        )


def test_long_full_bucket_reset_waits_only_for_next_turn_deficit(setup, monkeypatch):
    service, tracker, payloads = setup
    sleeps = []
    monkeypatch.setattr("services.groq_analysis.time.sleep", sleeps.append)
    with service.groq.session(reserved_tokens=1000, max_requests=1) as session:
        session.rate_headers = {
            "x-ratelimit-limit-tokens": "8000",
            "x-ratelimit-remaining-tokens": "2466",
            "x-ratelimit-reset-tokens": "41.504s",
        }
        session.rate_checked_at = time.monotonic()
        session._pace(3500)
    assert len(sleeps) == 1
    assert 7 < sleeps[0] < 9
