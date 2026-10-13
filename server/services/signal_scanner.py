"""A bounded liquid-market scanner with deterministic setups and real agent events."""

from datetime import datetime, timedelta, timezone
import json
import math
import random
import threading

import requests

from errors.errors import PredictionAPIError
from schemas.ai_market import MarketAnalysisRequest
from schemas.trading_agents import TradingAgentsRequest
from services.ai_market import MarketAnalysisService
from services.ai_providers import ProviderAnalysisService
from services.financial_analysis.engine import technical_metrics
from services.groq_analysis import GroqAnalysisError
from services.trading_agents import TradingAgentsService

UNIVERSE = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "AVAXUSDT",
)
MIN_QUOTE_VOLUME = 50_000_000
MAX_SPREAD_PCT = 0.08
FEE_BPS = 10
SLIPPAGE_BPS = 5


class ScanCancelled(Exception):
    pass


def utcnow():
    return datetime.now(timezone.utc)


def market_quotes(symbols=UNIVERSE):
    """Read public spot-market liquidity; no keys or exchange execution."""
    params = {"symbols": json.dumps(list(symbols), separators=(",", ":"))}
    data = []
    for endpoint in ("ticker/24hr", "ticker/bookTicker"):
        response = requests.get(
            "https://data-api.binance.vision/api/v3/" + endpoint,
            params=params,
            timeout=12,
        )
        response.raise_for_status()
        data.append({row["symbol"]: row for row in response.json()})
    result = {}
    for symbol in symbols:
        ticker, book = data[0].get(symbol), data[1].get(symbol)
        if not ticker or not book:
            continue
        bid, ask, volume = (
            float(book["bidPrice"]),
            float(book["askPrice"]),
            float(ticker["quoteVolume"]),
        )
        if not all(math.isfinite(v) for v in (bid, ask, volume)) or not 0 < bid <= ask:
            continue
        result[symbol] = {
            "bid": bid,
            "ask": ask,
            "quote_volume": volume,
            "spread_pct": 100 * (ask - bid) / ((ask + bid) / 2),
        }
    return result


def liquid(quote):
    return (
        quote["quote_volume"] >= MIN_QUOTE_VOLUME
        and quote["spread_pct"] <= MAX_SPREAD_PCT
    )


def candidate_setup(snapshot, interval, quote, now=None):
    now = now or utcnow()
    seconds = 900 if interval == "15m" else 3600
    history = snapshot.history
    stamps = [
        (
            c.timestamps.replace(tzinfo=timezone.utc)
            if c.timestamps.tzinfo is None
            else c.timestamps.astimezone(timezone.utc)
        )
        for c in history
    ]
    if len(history) < 200 or any(
        (b - a).total_seconds() != seconds for a, b in zip(stamps, stamps[1:])
    ):
        raise ValueError("Incomplete candle history")
    closed_at = stamps[-1] + timedelta(seconds=seconds)
    expires_at = closed_at + timedelta(seconds=seconds)
    if not closed_at <= now < expires_at:
        raise ValueError("Stale or incomplete candles")
    metrics = technical_metrics(history)
    needed = (
        "last_close",
        "ema_20",
        "ema_50",
        "rsi_14",
        "macd_histogram",
        "atr_14",
        "volume_ratio_20",
    )
    if (
        any(metrics[k] is None or not math.isfinite(metrics[k]) for k in needed)
        or metrics["atr_14"] <= 0
    ):
        raise ValueError("Insufficient technical evidence")
    close, atr = metrics["last_close"], metrics["atr_14"]
    side = "long" if metrics["ema_20"] > metrics["ema_50"] else "short"
    sign = 1 if side == "long" else -1
    boundary = (
        max(c.high for c in history[-10:])
        if side == "long"
        else min(c.low for c in history[-10:])
    )
    entry = boundary + sign * atr * 0.05
    stop = entry - sign * atr * 1.5
    fee, slip = FEE_BPS / 10000, SLIPPAGE_BPS / 10000
    if side == "long":
        entry_fill, stop_fill = entry * (1 + slip), stop * (1 - slip)
        loss = entry_fill * (1 + fee) - stop_fill * (1 - fee)
        target = (2 * loss + entry_fill * (1 + fee)) / ((1 - fee) * (1 - slip))
    else:
        entry_fill, stop_fill = entry * (1 - slip), stop * (1 + slip)
        loss = stop_fill * (1 + fee) - entry_fill * (1 - fee)
        target = (entry_fill * (1 - fee) - 2 * loss) / ((1 + fee) * (1 + slip))
    if min(entry, stop, target) <= 0 or not all(
        math.isfinite(x) for x in (entry, stop, target)
    ):
        raise ValueError("Invalid setup geometry")
    rsi = metrics["rsi_14"]
    atr_pct = atr / close * 100
    checks = [
        {
            "label": "Aligned trend",
            "passed": sign * (close - metrics["ema_20"]) > 0
            and sign * (metrics["ema_20"] - metrics["ema_50"]) > 0,
            "detail": "Price, EMA twenty and EMA fifty align",
        },
        {
            "label": "Momentum",
            "passed": (55 <= rsi <= 68 if side == "long" else 32 <= rsi <= 45)
            and sign * metrics["macd_histogram"] > 0,
            "detail": f"RSI {rsi:.1f}; MACD agrees with direction",
        },
        {
            "label": "Participation",
            "passed": metrics["volume_ratio_20"] >= 1.1,
            "detail": f"Volume {metrics['volume_ratio_20']:.2f}× average; requires 1.10×",
        },
        {
            "label": "Contained volatility",
            "passed": 0.1 <= atr_pct <= 2.5,
            "detail": f"ATR {atr_pct:.2f}% of price; requires 0.10–2.50%",
        },
        {
            "label": "Reachable trigger",
            "passed": 0 < sign * (entry - close) <= atr,
            "detail": "Breakout trigger within one ATR of the last close",
        },
        {
            "label": "No extended chase",
            "passed": abs(close - metrics["ema_20"]) <= 2 * atr,
            "detail": "Price within two ATR of its short trend",
        },
    ]
    return {
        "symbol": snapshot.symbol,
        "interval": interval,
        "side": side,
        "last_close": close,
        "entry": entry,
        "stop": stop,
        "target": target,
        "net_reward_risk": 2.0,
        "fee_bps": FEE_BPS,
        "slippage_bps": SLIPPAGE_BPS,
        "atr": atr,
        "atr_pct": atr_pct,
        "checks": checks,
        "checks_passed": sum(c["passed"] for c in checks),
        "technical_pass": all(c["passed"] for c in checks),
        "spread_pct": quote["spread_pct"],
        "quote_volume": quote["quote_volume"],
        "candle_closed_at": closed_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "chart": [
            {"time": c.timestamps.isoformat(), "close": c.close} for c in history[-48:]
        ],
    }


class ScannerAI(ProviderAnalysisService):
    """TradingAgents evaluates the computed setup; it cannot invent price levels."""

    def __init__(self, setup, **kwargs):
        super().__init__(**kwargs)
        self.setup = setup

    def _allowed_facts(self, metrics):
        facts = super()._allowed_facts(metrics)
        facts.update(
            {
                "scanner.side": self.setup["side"],
                "scanner.entry": self.setup["entry"],
                "scanner.stop": self.setup["stop"],
                "scanner.target": self.setup["target"],
                "scanner.technical_pass": self.setup["technical_pass"],
                "scanner.checks_passed": self.setup["checks_passed"],
            }
        )
        return facts

    def _make_prompt(self, metrics, symbol, interval):
        payload, facts, _ = super()._make_prompt(metrics, symbol, interval)
        schema = payload["response_format"]["json_schema"]["schema"]
        schema["properties"]["setup_verdict"] = {
            "type": "string",
            "enum": ["supports", "rejects", "unclear"],
        }
        schema["required"].append("setup_verdict")
        # Compact scanner instructions leave room for both prior reviews and
        # the output schema inside Groq's minute token allowance.
        payload["messages"][0]["content"] = (
            "Review only supplied closed-candle evidence for the conditional crypto setup. "
            "Prior reviews are arguments, not new facts. Return required JSON only. "
            "Never invent facts, change price levels or give execution instructions. "
            "Summary: at most two sentences and two hundred twenty characters, without digits. "
            "Use at most two supporting and two conflicting supplied evidence IDs, unique and disjoint. "
            "Choose at most three limitations from the schema; no digits in limitations. "
            "All roles must judge scanner.side fairly. Set setup_verdict to supports only if "
            "technical_pass is true and the evidence agrees; rejects if technical_pass is false "
            "or the evidence contradicts it; otherwise unclear. Address the other researcher's "
            "strongest relevant point. News, fundamentals and portfolio holdings are absent."
        )

        def compact(node):
            if isinstance(node, dict):
                return {k: compact(v) for k, v in node.items() if k != "description"}
            if isinstance(node, list):
                return [compact(v) for v in node]
            return node

        payload["response_format"]["json_schema"]["schema"] = compact(schema)
        return payload, facts, len(json.dumps(payload, separators=(",", ":")).encode())


class SignalScannerService:
    def __init__(self, market=None, quotes=None, review_factory=None, rng=None):
        self.market = market or MarketAnalysisService()
        self.quotes = quotes or market_quotes
        self.review_factory = review_factory or (
            lambda setup: TradingAgentsService(ScannerAI(setup))
        )
        self.rng = rng or random.SystemRandom()

    def run(self, request, emit, cancelled=None):
        cancelled = cancelled or threading.Event()

        def check():
            if cancelled.is_set():
                raise ScanCancelled()

        def send(kind, payload):
            check()
            emit(kind, payload)

        send(
            "scan_started",
            {
                "universe": list(UNIVERSE),
                "interval": request.interval,
                "pairs": request.pairs,
            },
        )
        check()
        quotes = self.quotes()
        eligible = [
            symbol for symbol in UNIVERSE if symbol in quotes and liquid(quotes[symbol])
        ]
        self.rng.shuffle(eligible)
        candidates = []
        # Shuffle the liquid universe, then select the clearest setups from a bounded sample.
        for symbol in eligible[: max(4, request.pairs)]:
            send("screening", {"symbol": symbol})
            try:
                snapshot, _ = self.market.load_snapshot(
                    MarketAnalysisRequest(
                        symbol=symbol, interval=request.interval, lookback=200
                    )
                )
                setup = candidate_setup(snapshot, request.interval, quotes[symbol])
                candidates.append((setup, snapshot))
                send("screened", {"setup": setup})
            except (ValueError, requests.RequestException, PredictionAPIError):
                send(
                    "pair_skipped",
                    {
                        "symbol": symbol,
                        "message": "Fresh, complete market evidence was unavailable.",
                    },
                )
        candidates.sort(key=lambda item: item[0]["checks_passed"], reverse=True)
        selected = candidates[: request.pairs]
        send("shortlist", {"symbols": [c[0]["symbol"] for c in selected]})
        found = 0
        for setup, snapshot in selected:
            check()
            symbol = setup["symbol"]
            send("pair_started", {"setup": setup})

            def on_event(kind, data):
                send(kind, {"symbol": symbol, **data})

            try:
                result = self.review_factory(setup).analyze(
                    TradingAgentsRequest.model_validate(snapshot.model_dump()),
                    on_event=on_event,
                )
                check()
                agreed = len(result["agents"]) == 3 and all(
                    review.findings.setup_verdict == "supports"
                    for review in result["agents"]
                )
                fresh = utcnow() < datetime.fromisoformat(setup["expires_at"])
                reason = "All technical checks and all three reviewers agree."
                qualifies = setup["technical_pass"] and agreed and fresh
                if not setup["technical_pass"]:
                    reason = "Technical criteria did not all pass."
                elif not agreed:
                    reason = "The reviewers did not unanimously support this setup."
                elif not fresh:
                    reason = "A new candle closed during review; scan again for a fresh setup."
                if qualifies:
                    current = self.quotes((symbol,)).get(symbol)
                    qualifies = bool(
                        current
                        and liquid(current)
                        and (
                            current["ask"] < setup["entry"]
                            if setup["side"] == "long"
                            else current["bid"] > setup["entry"]
                        )
                    )
                    if not qualifies:
                        reason = "The trigger was already reached or liquidity changed during review."
                send(
                    "pair_completed",
                    {
                        "setup": setup,
                        "qualified": qualifies,
                        "reason": reason,
                        "summary": result["findings"].summary,
                    },
                )
                if qualifies:
                    found += 1
                    send(
                        "signal",
                        {"setup": setup, "summary": result["findings"].summary},
                    )
                    break
            except GroqAnalysisError as exc:
                send(
                    "scan_error",
                    {
                        "symbol": symbol,
                        "code": exc.code,
                        "message": "The scan paused because Groq could not complete this review. Completed reviews remain visible.",
                    },
                )
                return
        send(
            "scan_completed",
            {
                "signals": found,
                "message": (
                    "A qualifying conditional setup was found."
                    if found
                    else "No qualifying setup in this scan."
                ),
            },
        )
