# Independent AI dashboard and OSS-120B fallback

Open `/ai-analysis` from the navigation. Select the market source, symbol, candle interval, completed history count, and assessment or TradingAgents review. Click **Analyze market**. The backend loads closed Binance or Yahoo Finance candles, computes Python indicators, and submits only the bounded numerical evidence. It never invokes forecasting inference or needs prediction output. Forecasting remains in its own workspace.

## Fixed model contract

| Order | Provider | Fixed request model | Fixed HTTPS endpoint |
|---|---|---|---|
| 1 | Groq | `openai/gpt-oss-120b` | `https://api.groq.com/openai/v1/chat/completions` |
| 2 | Routeway | `gpt-oss-120b` | `https://api.routeway.ai/v1/chat/completions` |
| 3 | OpenRouter | `openai/gpt-oss-120b` | `https://openrouter.ai/api/v1/chat/completions` |

Both IDs identify GPT-OSS-120B. No other model, size, automatic model router, model fallback array, or user-selected endpoint is accepted. A provider response must report one of these exact model aliases; missing or different model metadata is rejected after accounting for the attempt. HTTP redirects are refused. OpenRouter may select a backend serving this same requested model; `require_parameters` keeps the structured-output requirements. This never selects an alternate model.

Official API references: [Routeway OpenAI-compatible configuration](https://docs.routeway.ai/getting-started/chat-uis), [Routeway model catalog](https://routeway.ai/models), [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).

## Credentials

Configure backend environment variables `GROQ_API_KEY`, `ROUTEWAY_API_KEY`, and `OPENROUTER_API_KEY`, or private files `~/.config/kronos-studio/groq_key`, `routeway_key`, and `openrouter_key`. The file directory must be owned by the backend user with permissions 700, and each regular key file must have permissions 600. Restart the backend after changing its environment. Adding an account or credential to another application does not automatically configure this backend.

Keys are never placed in the repository, browser, API responses, or journal. The dashboard reads local connection status without contacting a provider. It distinguishes connected, unconfigured, exhausted, temporarily unavailable and tracking-unavailable providers.

## Immediate, bounded fallback

Before every turn, skip missing credentials, persistent cooldowns and known exhausted budgets. Groq keeps the existing assumed daily token/request allowances, 80% ceiling, cross-process lock and notification state. Remaining token/request headers can switch the next research turn before another rejected call is sent.

HTTP 429 (rate/quota exhaustion), HTTP 402 (credits exhausted), other upstream failures, transport failures or wrong model metadata immediately try the next eligible provider. There is no refill sleep, repeated attempt to the same provider within a turn, or fallback to another model. Exhaustion is persisted as a provider cooldown so subsequent manual requests skip it until the deadline. Request timeouts are bounded to twenty seconds; switching starts once failure is known.

A single assessment has one logical turn and at most three provider attempts. TradingAgents has three logical turns and at most nine attempts. A successfully selected provider is preferred for subsequent turns, with fallback still checked each time. If every configured provider is unavailable, stop with a fixed error. Invalid semantic findings stop after accounting; they are never silently accepted as a successful assessment.

Every attempt is recorded in private `~/.local/share/kronos-ai/usage.jsonl`: provider, fixed model, timestamp, token estimate/reported usage, HTTP status and reported cost when supplied. No prompts, responses or credentials are stored there. Groq attempts also update the original private Groq recorder; milestones are not acknowledged by the dashboard. In-flight and uncertain transport attempts are conservatively accounted for.

Routeway and OpenRouter account allowances are not invented. Their locally recorded token/request counts are shown, with unknown allowance/percentage unless configured. Optional private `~/.config/kronos-studio/provider_limits.json` can supply positive daily `tokens` and `requests` integers for each provider; those known budgets use the same 80% ceiling. External usage in other apps is not necessarily visible here. Provider credit/quota failures remain authoritative even when local limits are unknown.

## API and verification

- `GET /api/analysis/providers`: local connection, usage and availability metadata; no provider request.
- `POST /api/analysis/market`: symbol, interval, lookback (35–999), data source, optional Yahoo period, mode (`single` or `agents`). Forecast and model-selection fields are forbidden.
- Legacy `/api/analysis/groq` and `/api/analysis/trading-agents` accept validated snapshots and use the same fixed provider chain.

Loopback and allowed-origin checks apply to every analysis route. Only manual submission starts analysis. Changing settings clears results and discards stale browser responses; an abort cannot undo a provider call already accepted by the backend.

Verification: **151 backend tests passed**, along with frontend TypeScript, lint and production build. Backend tests cover exact IDs for all three providers, wrong-model rejection, credits/rate-limit fallback without sleeping, known quota preflight, uncertain-attempt accounting, persisted cooldowns and independent three-role analysis. Desktop/mobile checks cover manual invocation, duplicate clicks, stale results, safe errors, source changes and no prediction requests. Live assessment was verified with Groq and 200 completed candles; Routeway/OpenRouter use controlled transport tests because their credentials were unavailable to the backend during validation.
