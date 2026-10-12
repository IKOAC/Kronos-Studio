# Groq analysis (Phases 2–3)

## Scope

Two **read-only, loopback-only** API routes are registered:

- `GET /api/analysis/groq/usage` — returns recorded token/request usage and pending 5% alerts without calling Groq.
- `POST /api/analysis/groq` — validates completed OHLCV data, executes the local deterministic engine, submits a compact **calculated metrics snapshot** to Groq's `openai/gpt-oss-120b`, validates the structured response, and returns both the original numerical metrics and bounded qualitative findings.

The frontend offers manual analysis of an existing forecast. There is no automatic trade execution, additional market-data fetching, backtesting, or TradingAgents integration. `main` remains unchanged during development. The existing `POST /api/analysis/metrics` endpoint continues to work without Groq.

## Authentication and network boundary

- The credential is loaded only by the backend from `~/.config/kronos-studio/groq_key`, a regular file owned by the current user with no group or other permissions, inside a private directory. **The key must never be copied to the repo, returned in a response, or included in logs or browser code.**
- The API rejects non-loopback clients (IPv4/IPv6) and browser `Origin` values other than `http://localhost:3000`, `http://127.0.0.1:3000` and `http://[::1]:3000`.
- These local-only controls reduce remote unauthorized API usage; local processes running as the logged-in user can still make requests. For public/network deployments, implement real user authentication and separate per-user budgets before enabling this API.
- TLS peer verification is required, using the system certificate bundle. On the tested Mac `/etc/ssl/cert.pem` is used. The only outgoing host is `api.groq.com`. HTTP failures return fixed error codes without exposing provider response bodies.
- If the tracker or credential cannot be opened securely, **no Groq request is issued**.

## Mandatory quota accounting

The existing private quota tracker at `~/.local/share/kronos-groq/monitor.py` is used directly. Existing usage logs and the configured hourly 5%-milestone notification are preserved. A versioned reference copy lives at `scripts/groq_usage_monitor.py`; the backend still loads the private installed copy. Both copies count every locally recorded attempt and use the larger of that count and the latest provider checkpoint plus subsequent uncertain attempts, so a decreasing or repeated provider header cannot erase local usage.

- Preflight uses the latest recorded daily consumption, with an **80% hard ceiling** on both estimated daily token allowance and account request allowance.
- The estimate reserves the complete UTF-8 serialized prompt bytes (conservative token proxy), maximum completion tokens, and additional headroom **before** allowing a request. The API returns HTTP 429 without calling Groq if the estimate would exceed the ceiling.
- An OS file lock at `~/.local/share/kronos-groq/analysis.lock` serializes preflight and request recording across backend processes.
- Provider-reported usage and request-rate-limit headers are appended to the **same** usage log. Missing provider usage is conservatively estimated. A transport failure is conservatively recorded as an unconfirmed request with estimated token usage.
- The API response exposes `pending_5pct_alerts` but does not acknowledge them; the user's existing monitoring automation handles notifications and acknowledgment.
- Only calls routed through the local tracker are included in observed token totals. Other apps or keys may consume the account allowance without appearing in these totals. Published free-tier limits are **assumptions subject to Groq's actual account limits**.

## Request and response contracts

`POST /api/analysis/groq` expects the Phase 1 `FinancialAnalysisRequest` fields plus optional `symbol` and `interval`. Required `history` is a list of **closed, chronologically ordered** OHLCV candles (2–10,000). Optional `forecasts` supply final closing prices for named models; optional `trade` supplies hypothetical risk inputs.

The response contains:

- `metrics`: the unchanged numerical result of the deterministic Python financial engine, including technical metrics, unweighted forecast statistics, and hypothetical risk metrics.
- `forecast_consensus`: mechanically derived from the numeric forecast comparison (`up`, `down`, `flat`, `mixed`, or `insufficient`), never chosen by Groq.
- `findings`: Groq's short text summary, evidence IDs, conflicting evidence IDs, and limitations. The model is not allowed to provide substitute calculations or live trade signals.
- `quota`: UTC day, token/request usage, the configured ceiling and any unacknowledged 5% milestones.

Strict JSON Schema constrains the model response. Pydantic checks length, unique evidence identifiers, and numerical-claim restrictions; the server checks every referenced evidence ID against the actual computed facts. Invalid or incomplete outputs are rejected (HTTP 502) **after metering the provider request**, not silently accepted or automatically retried.

### Local smoke example (synthetic data)

```json
{
  "symbol": "BTCUSDT",
  "interval": "1h",
  "history": [
    {"timestamps": "2026-01-01T00:00:00", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10},
    {"timestamps": "2026-01-01T01:00:00", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10}
  ],
  "forecasts": [
    {"model_name": "kronos-mini", "final_close": 102},
    {"model_name": "chronos-2", "final_close": 98}
  ]
}
```

The example represents **synthetic**, not live, market candles or signals. For numerical signal tests, use a longer candle history to warm up RSI, MACD, and moving averages.

## Verification

Run `cd server && uv run --no-sync pytest -q`. Integration tests use a fake transport, fake quota recorder, and a fake private key to exercise success, invalid output, quota caps, origin guards, and failure paths **without consuming real Groq tokens**.

## Frontend

The compact AI analysis panel appears below the chart and model comparison for the selected single or batch result. The API helper sends only historical OHLCV candles and each model's final forecast close; it never includes local file paths or credentials. A local CSV forecast must have a valid market symbol to be analyzed.

Only clicking **Analyze with Groq** sends a POST. The panel never automatically retries. Its initial usage GET reads the local tracker without calling Groq. Loading blocks duplicate clicks; changing the selected result resets the panel and aborts stale browser responses. Aborting a browser request does not undo a provider call already accepted by the backend; those calls remain metered.

The panel displays Python RSI, MACD, EMA, ATR, agreement and dispersion separately from Groq's qualitative findings. Evidence values come from the returned Python metrics. Null metrics display an em dash. Known API errors use fixed frontend messages; arbitrary provider responses and validation inputs are never displayed. Recorded usage is refreshed after failures as well as successful analyses; pending milestone alerts are never acknowledged by the UI.

Frontend checks: `npx tsc --noEmit`, `npm run lint`, `npm run build`.
