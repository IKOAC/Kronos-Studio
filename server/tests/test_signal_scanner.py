from datetime import datetime, timedelta, timezone
import json
import random
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from main import app
from routers.signal_scanner import _scanner, _scan_lock
from schemas.financial_analysis import TradeInput
from schemas.groq_analysis import GroqAnalysisRequest, GroqFindings
from schemas.signal_scanner import SignalScannerRequest
from schemas.trading_agents import AgentReview
from services.financial_analysis.engine import trade_metrics
from services.groq_analysis import GroqAnalysisError
from services.signal_scanner import (
    SignalScannerService,
    ScanCancelled,
    ScannerAI,
    candidate_setup,
    liquid,
)


@pytest.fixture
def snapshot():
    now = datetime.now(timezone.utc)
    boundary = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
    history = [
        dict(
            timestamps=boundary - timedelta(minutes=15 * (200 - i)),
            open=100,
            high=100.2,
            low=99.8,
            close=100,
            volume=100,
        )
        for i in range(200)
    ]
    return GroqAnalysisRequest(symbol="BTCUSDT", interval="15m", history=history)


@pytest.fixture
def quote():
    return dict(bid=100, ask=100.01, quote_volume=100_000_000, spread_pct=0.01)


@pytest.fixture
def good_metrics(monkeypatch):
    metrics = dict(
        last_close=100,
        ema_20=99.8,
        ema_50=99.5,
        rsi_14=60,
        macd_histogram=0.1,
        atr_14=1,
        volume_ratio_20=1.2,
    )
    monkeypatch.setattr("services.signal_scanner.technical_metrics", lambda _: metrics)
    return metrics


@pytest.mark.parametrize("side", ["long", "short"])
def test_conditional_levels_have_two_to_one_net_reward_after_costs(
    snapshot, quote, good_metrics, side
):
    if side == "short":
        good_metrics.update(ema_20=100.2, ema_50=100.5, rsi_14=40, macd_histogram=-0.1)
    setup = candidate_setup(snapshot, "15m", quote)
    assert setup["side"] == side
    assert setup["technical_pass"]
    trade = TradeInput(
        side=side,
        entry=setup["entry"],
        stop=setup["stop"],
        target=setup["target"],
        fee_bps=setup["fee_bps"],
        slippage_bps=setup["slippage_bps"],
        account_equity=1000,
        risk_percent=1,
    )
    assert trade_metrics(trade)["net_reward_to_risk"] == pytest.approx(2)
    assert setup["checks_passed"] == 6


@pytest.mark.parametrize(
    "field,value",
    [("rsi_14", 90), ("volume_ratio_20", 0.8), ("atr_14", 5), ("ema_20", 95)],
)
def test_failed_checks_never_become_technical_pass(
    snapshot, quote, good_metrics, field, value
):
    good_metrics[field] = value
    assert not candidate_setup(snapshot, "15m", quote)["technical_pass"]


def test_stale_or_gapped_candles_are_rejected(snapshot, quote, good_metrics):
    with pytest.raises(ValueError):
        candidate_setup(
            snapshot, "15m", quote, now=datetime.now(timezone.utc) + timedelta(hours=1)
        )
    snapshot.history[100].timestamps += timedelta(seconds=1)
    with pytest.raises(ValueError):
        candidate_setup(snapshot, "15m", quote)


def test_insufficient_liquidity_is_excluded(quote):
    assert liquid(quote)
    assert not liquid({**quote, "quote_volume": 1000})
    assert not liquid({**quote, "spread_pct": 1})


def build_service(snapshot, quote, verdict="supports", price_moved=False):
    calls = []

    def quotes(symbols=None):
        result = {s: dict(quote) for s in (symbols or ("BTCUSDT", "ETHUSDT"))}
        if symbols and price_moved:
            for q in result.values():
                q.update(ask=102, bid=101.99)
        return result

    class Market:
        def load_snapshot(self, request):
            return snapshot.model_copy(update={"symbol": request.symbol}), {}

    class Review:
        def analyze(self, request, on_event):
            calls.append(request.symbol)
            reviews = []
            for role in ("bull", "bear", "research_manager"):
                on_event("agent_started", {"role": role})
                findings = GroqFindings(
                    summary="Evidence supports the proposed direction.",
                    supporting_evidence_ids=[],
                    conflicting_evidence_ids=[],
                    limitations=[],
                    setup_verdict=verdict,
                )
                review = AgentReview(role=role, findings=findings)
                reviews.append(review)
                on_event("agent_completed", review.model_dump())
            return {"agents": reviews, "findings": reviews[-1].findings}

    return (
        SignalScannerService(
            market=Market(),
            quotes=quotes,
            review_factory=lambda _: Review(),
            rng=random.Random(7),
        ),
        calls,
    )


def test_stops_on_first_qualified_signal_and_streams_actual_review_order(
    snapshot, quote, good_metrics
):
    service, calls = build_service(snapshot, quote)
    events = []
    service.run(SignalScannerRequest(), lambda kind, data: events.append((kind, data)))
    assert len(calls) == 1
    assert [e[1]["role"] for e in events if e[0] == "agent_completed"] == [
        "bull",
        "bear",
        "research_manager",
    ]
    assert len([e for e in events if e[0] == "signal"]) == 1
    assert events[-1][1]["signals"] == 1


@pytest.mark.parametrize(
    "verdict,moved,technical",
    [
        ("unclear", False, True),
        ("rejects", False, True),
        ("supports", True, True),
        ("supports", False, False),
    ],
)
def test_no_signal_for_disagreement_changed_entry_or_failed_checks(
    snapshot, quote, good_metrics, verdict, moved, technical
):
    if not technical:
        good_metrics["volume_ratio_20"] = 0.5
    service, calls = build_service(snapshot, quote, verdict, moved)
    events = []
    service.run(SignalScannerRequest(), lambda kind, data: events.append((kind, data)))
    assert len(calls) == 2
    assert not any(kind == "signal" for kind, _ in events)
    assert events[-1][1]["signals"] == 0


def test_cancellation_prevents_the_next_role(snapshot, quote, good_metrics):
    service, calls = build_service(snapshot, quote)
    cancelled = threading.Event()
    events = []

    def emit(kind, data):
        events.append(kind)
        if kind == "agent_completed":
            cancelled.set()

    with pytest.raises(ScanCancelled):
        service.run(SignalScannerRequest(), emit, cancelled)
    assert events.count("agent_started") == 1
    assert events.count("agent_completed") == 1
    assert len(calls) == 1


def test_quota_error_is_terminal_and_preserves_specific_code(
    snapshot, quote, good_metrics
):
    service, _ = build_service(snapshot, quote)

    class Failure:
        def analyze(self, *args, **kwargs):
            raise GroqAnalysisError(429, "GROQ_DAILY_CAP", "private upstream text")

    service.review_factory = lambda _: Failure()
    events = []
    service.run(SignalScannerRequest(), lambda kind, data: events.append((kind, data)))
    assert events[-1][0] == "scan_error"
    assert events[-1][1]["code"] == "GROQ_DAILY_CAP"
    assert "private upstream text" not in json.dumps(events)


def test_request_does_not_allow_arbitrary_pairs_models_or_unbounded_runs():
    for body in (
        {"pairs": 4},
        {"pairs": 0},
        {"symbol": "UNKNOWN"},
        {"model": "other"},
        {"interval": "1m"},
    ):
        with pytest.raises(ValidationError):
            SignalScannerRequest.model_validate(body)


def test_stream_endpoint_is_local_bounded_and_serializes_events(
    snapshot, quote, good_metrics
):
    service, _ = build_service(snapshot, quote)
    app.dependency_overrides[_scanner] = lambda: service
    try:
        with TestClient(app, client=("127.0.0.1", 123)) as client:
            response = client.post("/api/analysis/scanner/stream", json={})
            assert response.status_code == 200
            events = [json.loads(line) for line in response.text.splitlines()]
            assert events[0]["type"] == "scan_started"
            assert events[-1]["type"] == "scan_completed"
            assert response.headers["content-type"].startswith("application/x-ndjson")
            assert (
                client.post(
                    "/api/analysis/scanner/stream",
                    json={},
                    headers={"origin": "https://example.com"},
                ).status_code
                == 403
            )
            assert _scan_lock.acquire(blocking=False)
            try:
                assert (
                    client.post("/api/analysis/scanner/stream", json={}).status_code
                    == 409
                )
            finally:
                _scan_lock.release()
    finally:
        app.dependency_overrides.pop(_scanner, None)


def test_scanner_uses_real_three_role_flow_and_bounded_prompts(
    snapshot, quote, good_metrics, tmp_path
):
    from test_groq_analysis import MockTracker
    from services.trading_agents import TradingAgentsService

    keydir = tmp_path / "keys"
    keydir.mkdir(mode=0o700)
    keyfile = keydir / "groq_key"
    keyfile.write_text("test_private_token_" * 3)
    keyfile.chmod(0o600)
    payloads = []

    def transport(provider, payload, key):
        payloads.append(payload)
        assert (
            "setup_verdict"
            in payload["response_format"]["json_schema"]["schema"]["required"]
        )
        content = dict(
            summary="Evidence supports the proposed direction.",
            supporting_evidence_ids=["technical.rsi_14"],
            conflicting_evidence_ids=[],
            limitations=[],
            setup_verdict="supports",
        )
        return (
            200,
            {
                "model": provider.model,
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(content)},
                    }
                ],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 200},
            },
            {
                "x-ratelimit-limit-tokens": "8000",
                "x-ratelimit-remaining-tokens": "8000",
                "x-ratelimit-reset-tokens": "0s",
            },
        )

    ai = ScannerAI(
        candidate_setup(snapshot, "15m", quote),
        key_directory=keydir,
        journal_root=tmp_path / "journal",
        groq_tracker=MockTracker(),
        provider_transport=transport,
        lock_path=tmp_path / "lock",
    )
    events = []
    result = TradingAgentsService(ai).analyze(
        snapshot, on_event=lambda kind, data: events.append((kind, data))
    )
    assert len(payloads) == len(result["agents"]) == 3
    assert len(events) == 6
    assert "Bull Analyst" in payloads[1]["messages"][1]["content"]
    assert "Bear Analyst" in payloads[2]["messages"][1]["content"]


def test_browser_schema_accepts_actual_stream_contract(snapshot, quote, good_metrics):
    import shutil
    import subprocess
    from pathlib import Path

    frontend = Path(__file__).resolve().parents[2] / "frontend"
    if not shutil.which("node") or not (frontend / "node_modules/typescript").exists():
        pytest.skip(
            "Frontend dependencies are required for the cross-language contract check"
        )
    service, _ = build_service(snapshot, quote)
    app.dependency_overrides[_scanner] = lambda: service
    try:
        with TestClient(app, client=("127.0.0.1", 123)) as client:
            response = client.post("/api/analysis/scanner/stream", json={})
        script = r"""
const fs=require("fs"), ts=require("typescript");
const source=fs.readFileSync("src/schemas/signalScannerSchema.ts","utf8");
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const mod={exports:{}};
new Function("require","module","exports",compiled)(require,mod,mod.exports);
const events=fs.readFileSync(0,"utf8").trim().split("\n").map(line=>mod.exports.ScannerEventSchema.parse(JSON.parse(line)));
if(!events.some(event=>event.type==="signal"))throw Error("Missing signal contract");
"""
        subprocess.run(
            ["node", "-e", script],
            cwd=frontend,
            input=response.text,
            text=True,
            capture_output=True,
            check=True,
            timeout=15,
        )
    finally:
        app.dependency_overrides.pop(_scanner, None)
