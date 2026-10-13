# Groq OSS-120B analysis

The `/ai-analysis` dashboard currently uses Groq only. Market assessment and all three research roles use `openai/gpt-oss-120b` at `https://api.groq.com/openai/v1/chat/completions`, with high reasoning effort. Additional providers can be added later. No paid fallback or alternative model is configured.

Configure `GROQ_API_KEY` in the backend environment or a private `~/.config/kronos-studio/groq_key` file. The directory must be owned by the backend user with permissions 700 and the key file with permissions 600. Credentials never reach the browser, journal, or API responses.

## Status and limits

`GET /api/analysis/providers` returns only Groq connection, local quota, and cooldown metadata. It makes no generation or account-balance requests. Ready indicates credentials and local daily quota are available; it does not promise that an entire multi-turn review fits the current minute allowance.

Every turn reserves its completion budget against the existing 80% daily usage ceiling. A request that would exceed that ceiling returns `GROQ_DAILY_CAP`. Between research turns, the backend honors Groq's minute token limit, remaining-token and refill headers. It waits only for the needed deficit, for at most forty-five seconds per turn. If the request would require a longer wait or exceed the minute limit, it returns `GROQ_RATE_LIMITED`, rather than a generic unavailable error. HTTP 429 and provider cooldowns also return the rate-limit error.

## Generation and recovery

High reasoning and final JSON share a bounded 4,096-token completion budget. Each turn permits at most one retry, either after an upstream HTTP 502/503/504 (with a one-second pause) or after Groq's HTTP 400 `json_validate_failed` code. The JSON failure uses immediate recovery using JSON-object mode, with the same schema supplied in the prompt and reasoning hidden. Python findings and evidence checks remain enforced. Both attempts are metered; failed generation receives a conservative token estimate and quota is checked again before recovery. JSON-generation failures do not place Groq in cooldown.

A single assessment has one logical turn and at most two attempts. The three-role review has three logical turns and at most six attempts. There is no model fallback or unbounded retry. The backend validates model metadata and qualitative findings before accepting a result. Provider rejections, wrong models, invalid output, quota limits, and transport failures have distinct errors. Each high-reasoning inference request has a bounded forty-five-second timeout; transport failures retain a specific connection-failure status.

Every attempt is recorded in private `~/.local/share/kronos-ai/usage.jsonl`, and Groq usage also updates the existing private quota recorder. No prompts, response bodies, or credentials are stored. Historical usage records are retained.

## Dashboard flow

Select the market source, symbol, interval, completed candle count, and single assessment or research review. On manual submission the backend retrieves completed Binance or Yahoo Finance candles, excludes the forming candle, and computes numerical evidence in Python. The result is fixed until another submission. Forecasting remains independent.

- `GET /api/analysis/providers`: Groq status and local quota, without inference.
- `POST /api/analysis/market`: source, symbol, interval, history, and single or agents mode.
- Legacy `/api/analysis/groq` and `/api/analysis/trading-agents`: validated numerical snapshots using the same Groq-only service.
