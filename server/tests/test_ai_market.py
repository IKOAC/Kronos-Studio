"""Independent analysis loads candles and never runs forecasting inference."""

from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from main import app
from routers.ai_market import _service
from schemas.ai_market import MarketAnalysisRequest
from services.ai_market import MarketAnalysisService
from services.financial_analysis.engine import analyze_financials
from test_groq_analysis import valid_response
from test_ai_providers import setup as provider_setup


class Candles:
    def __init__(self):
        self.calls = []

    def get_data_from_binance(self, **kwargs):
        self.calls.append(kwargs)
        start = datetime.now(timezone.utc) - timedelta(days=1)
        rows = [
            dict(
                timestamps=start + timedelta(minutes=5 * i),
                open=100,
                high=101,
                low=99,
                close=100,
                volume=10,
                amount=1000,
            )
            for i in range(kwargs["lookback"])
        ]
        return {"df": pd.DataFrame(rows)}


class AI:
    def __init__(self):
        self.snapshots = []

    def analyze(self, snapshot):
        self.snapshots.append(snapshot)
        return {
            "symbol": snapshot.symbol,
            "interval": snapshot.interval,
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
            "metrics": analyze_financials(snapshot),
            "findings": {
                "summary": "Momentum is neutral.",
                "supporting_evidence_ids": ["technical.rsi_14"],
                "conflicting_evidence_ids": [],
                "limitations": [],
            },
            "forecast_consensus": "insufficient",
            "quota": {
                "day_utc": "2026-10-13",
                "token_limit_assumed": 200000,
                "tokens_observed": 100,
                "token_percent_observed": 0.05,
                "requests_limit": 1000,
                "requests_used": 1,
                "requests_percent_used": 0.1,
                "usage_percent": 0.1,
                "cap_percent": 80,
                "pending_5pct_alerts": [],
            },
        }


@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides.clear()


def test_market_route_accepts_symbol_without_any_prediction(monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("Forecast inference must not run")

    monkeypatch.setattr(
        "services.prediction_service.price_prediction.PricePredictionService.predict_price",
        forbidden,
    )
    data, ai = Candles(), AI()
    app.dependency_overrides[_service] = lambda: MarketAnalysisService(data, ai)
    with TestClient(app, client=("127.0.0.1", 54321)) as c:
        result = c.post(
            "/api/analysis/market",
            json={"symbol": "ethusdt", "interval": "5m", "lookback": 40},
        )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["symbol"] == "ETHUSDT"
    assert body["metrics"]["forecast"] is None
    assert body["market_data"]["candles"] == 40
    assert ai.snapshots[0].forecasts == []
    assert data.calls[0]["pred_len"] == 1  # timestamp preparation only


@pytest.mark.parametrize("field", ["model", "models", "api_url", "prompt", "forecasts"])
def test_market_route_rejects_model_override_or_required_forecast_injection(field):
    with TestClient(app, client=("127.0.0.1", 54321)) as c:
        r = c.post(
            "/api/analysis/market", json={"symbol": "ETHUSDT", field: "arbitrary"}
        )
    assert r.status_code == 422


def test_market_route_reuses_local_origin_guards():
    with TestClient(app, client=("192.168.1.10", 54321)) as c:
        r = c.post("/api/analysis/market", json={"symbol": "ETHUSDT"})
    assert r.status_code == 403


def test_independent_agents_review_preserves_all_three_roles_without_forecasts(
    provider_setup,
):
    service, tracker, calls, _ = provider_setup
    original = service.provider_transport

    def transport(provider, payload, key):
        status, body, headers = original(provider, payload, key)
        body["choices"][0]["message"]["content"] = __import__("json").dumps(
            {
                "summary": "Technical momentum is neutral.",
                "supporting_evidence_ids": ["technical.rsi_14"],
                "conflicting_evidence_ids": [],
                "limitations": [
                    "Historical indicators do not guarantee future outcomes."
                ],
            }
        )
        return status, body, headers

    service.provider_transport = transport
    app.dependency_overrides[_service] = lambda: MarketAnalysisService(
        Candles(), service
    )
    with TestClient(app, client=("127.0.0.1", 54321)) as c:
        response = c.post(
            "/api/analysis/market",
            json={"symbol": "ETHUSDT", "lookback": 40, "mode": "agents"},
        )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metrics"]["forecast"] is None
    assert result["run_stats"]["requests_used"] == 3
    assert [item["role"] for item in result["agents"]] == [
        "bull",
        "bear",
        "research_manager",
    ]
    assert len(calls) == 3
    assert all(payload["model"] == "openai/gpt-oss-120b" for _, payload in calls)
