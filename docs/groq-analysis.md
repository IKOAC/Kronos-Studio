# Groq analysis (Phases 2–3)

## Scope

Two **read-only, loopback-only** API routes are registered:

- `GET /api/analysis/groq/usage` — returns recorded token/request usage and pending 5% alerts without calling Groq.
- `POST /api/analysis/groq` — validates completed OHLCV data, executes the local deterministic engine, submits a compact **calculated metrics snapshot** to Groq's `openai/gpt-oss-120b`, validates the structured response, and returns both the original numerical metrics and bounded qualitative findings.

The independent **AI analysis** dashboard at `/ai-analysis` loads completed market candles without running predictions. Both assessment and TradingAgents review use the Groq-only service documented in `docs/ai-providers.md`. The legacy snapshot routes remain available. There is no automatic trade execution or backtesting. The bounded TradingAgents research profile is documented in `docs/trading-agents.md`. `main` remains unchanged during development. The existing `POST /api/analysis/metrics` endpoint continues to work without Groq.

## Authentication and network boundary

- The credential is loaded only by the backend from `~/.config/kronos-studio/groq_key`, a regular file owned by the current user with no group or other permissions, inside a private directory. **The key must never be copied to the repo, returned in a response, or included in logs or browser code.**
- The API rejects non-loopback clients (IPv4/IPv6) and browser `Origin` values other than `http://localhost:3000`, `http://127.0.0.1:3000` and `http://[::1]:3000`.
- These local-only controls reduce remote unauthorized API usage; local processes running as the logged-in user can still make requests. For public/network deployments, implement real user authentication and separate per-user budgets before enabling this API.
- TLS peer verification is required, using the system certificate bundle. On the tested Mac `/etc/ssl/cert.pem` is used. Provider calls use only the three fixed HTTPS endpoints documented in `docs/ai-providers.md`; redirects are refused. HTTP failures return fixed error codes without exposing provider response bodies.
- If the tracker or credential cannot be opened securely, **no Groq request is issued**.

## Mandatory quota accounting

The existing private quota tracker at `~/.local/share/kronos-groq/monitor.py` is used directly. Existing usage logs and the configured hourly 5%-milestone notification are preserved. A versioned reference copy lives at `scripts/groq_usage_monitor.py`; the backend still loads the private installed copy. Both copies count every locally recorded attempt and use the larger of that count and the latest provider checkpoint plus subsequent uncertain attempts, so a decreasing or repeated provider header cannot erase local usage.

- Preflight uses the latest recorded daily consumption, with an **80% hard ceiling** on both estimated daily token allowance and account request allowance.
- The estimate reserves the complete UTF-8 serialized prompt bytes (conservative token proxy), maximum completion tokens, and additional headroom **before** allowing a request. The chain skips Groq and immediately tries the next configured provider if this estimate would exceed the ceiling.
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

Strict JSON Schema constrains the response evidence IDs and known limitations using per-snapshot enums. Pydantic checks length, unique evidence identifiers, and numerical-claim restrictions; the server checks every referenced evidence ID against the actual computed facts. Invalid or incomplete outputs are rejected (HTTP 502) **after metering the provider request**, not silently accepted or automatically retried.

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

AI analysis has an independent dashboard at `/ai-analysis`. The forecasting workspace also has a separate **Analyze with Groq** / **TradingAgents review** panel below the selected single or batch forecast. That panel includes the selected forecast, all available model comparisons, and the current result's completed candle history, then discards/aborts its displayed analysis when the selected forecast changes. It shows the local usage tracker and the 80% ceiling; requests are never started automatically. The standalone dashboard needs a market symbol, source, interval and completed candle count; predictions and model weights are unnecessary. A single assessment or three-role review is started only by **Analyze market**. Initial load and **Refresh status** read local Groq connection, quota and cooldown metadata without model-generation or balance-reporting requests. See `docs/ai-providers.md` for limits and recovery behavior.

Loading blocks duplicate clicks. Changing settings resets findings and aborts stale browser responses. Aborting a browser request does not undo a provider call already accepted by the backend; those calls remain metered. Python metrics and evidence are displayed separately from the qualitative assessment. Unknown provider allowances remain unknown. Errors use fixed frontend messages and do not echo provider bodies or validation inputs.

Frontend checks: `npx tsc --noEmit`, `npm run lint`, `npm run build`.

Phase 4–5 validation and live token benchmarks: `docs/phase4-5-validation.md`.
