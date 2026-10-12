# TradingAgents research review (Phase 5)

Select **TradingAgents review** in the independent `/ai-analysis` dashboard and click **Analyze market**. It loads completed market candles directly; predictions are optional in the legacy snapshot API and unnecessary in the dashboard. A run has three logical research turns, each bounded to one attempt per configured provider, and resets when market settings change. It displays the research-manager assessment, expandable bull/bear findings, Python metrics, and recorded cost/time for that run.

## Integration boundary

The research-node subset is pinned to [TauricResearch/TradingAgents commit 1394a3f](https://github.com/TauricResearch/TradingAgents/tree/1394a3f72aa4393e1a98f51b382434c4b4c2d972) (v0.6.0). Modified upstream node factories are in `server/vendor/tradingagents/`, with Apache-2.0 license and modification notices. Their `.invoke()` interface is connected to the shared metered OSS-120B provider service. No additional dependencies were installed.

The fixed `snapshot_debate_v1` profile performs one bull interpretation, one bear response, and research-manager synthesis. Prompts are adapted to the existing financial evidence rather than company growth/portfolio recommendations. This integration uses the pinned research nodes; it does not run the full upstream LangGraph, external analyst/data tools, trading/portfolio agents, persistent memory or CLI. News, sentiment, company fundamentals and portfolio holdings are explicitly absent. Adding any of them requires its own source and quota design.

Python computes every number once. All three agents receive the same immutable evidence keys; earlier agent arguments are interpretations and never become numeric evidence. The resulting metrics are checked for mutation and returned separately. The deterministic forecast consensus remains unchanged. Agents cannot place orders or execute trades.

## API

`POST /api/analysis/trading-agents` accepts the Groq market snapshot contract. Extra workflow/prompt/tool fields are rejected. Loopback and origin guards are shared with Groq analysis.

Response extends the existing Groq response with:

- `agents`: bull, bear and research-manager findings, in execution order.
- `snapshot_id`: SHA-256 of the normalized input snapshot.
- `run_stats`: profile, actual provider request count, locally metered tokens, elapsed milliseconds, conservative reserved tokens and pinned upstream revision.

The existing `POST /api/analysis/groq` uses the same provider chain. Its usage endpoint retains the original Groq tracker. The new `POST /api/analysis/market` accepts market settings and `mode: "agents"`; `GET /api/analysis/providers` reads local connection and quota status. See `docs/ai-providers.md`.

## Quota and failure behavior

- Before the first call, the complete three-call worst-case reservation is checked under the existing cross-process lock: 34,086 tokens and three requests. This is a conservative reservation, not an expected billable cost. The lock covers the complete run; daily limits are rechecked before each turn.
- Each prompt is capped at 10,000 serialized bytes and each completion at 850 tokens. There is one turn per role. A provider failure immediately tries the next available provider for that turn, always using OSS-120B. There are at most nine total attempts; no provider is retried within the same turn.
- The default provider chain never sleeps for token refill. A reported exhausted token/request allowance switches the next turn immediately; HTTP 429 or 402 switches the current turn immediately. Provider cooldowns are persisted and skipped on later manual runs. A legacy isolated Groq service retains its bounded pacing for compatibility tests; all default API analysis routes use the new chain.
- The existing private log now also records provider minute-limit metadata. Its daily token assumptions, notification state and unacknowledged milestones are preserved. The browser never acknowledges alerts.
- Evidence IDs are constrained to a per-snapshot enum during generation. Limitations come from a bounded known list. Python independently checks narrative lengths, numeric-claim restrictions, duplicate/unknown/overlapping evidence IDs and completed output. Unsupported strict-schema keywords are avoided.
- If every configured provider fails, subsequent turns stop. Invalid semantic findings also stop the run after metering. Partial attempts are not returned as a successful complete review. The UI reads current usage after an error without repeating the analysis.

[Groq rate-limit documentation](https://console.groq.com/docs/rate-limits) defines the header scopes; [structured-output documentation](https://console.groq.com/docs/structured-outputs) defines strict-mode enum behavior. The daily ceiling remains eighty percent of the recorded assumed allowance.

## Verification

Backend: `cd server && uv run --no-sync pytest -q`.
Frontend: `cd frontend && npx tsc --noEmit && npm run lint && npm run build`.

Regression tests cover whole-run reservation, quota races, changing provider limits, invalid evidence at every turn, extra client fields, origin guards, snapshot identity, token accounting, rate pacing and candle completion. Browser checks cover manual invocation, duplicate clicks, selected batch market, reset/stale responses, safe errors and mobile layout.

See `docs/phase4-5-validation.md` for real-model validation and the measured live benchmark.
