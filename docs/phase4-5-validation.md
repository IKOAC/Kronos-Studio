# Phase 4 and Phase 5 validation

**Completed:** October 13, 2026 (Asia/Kolkata). Live benchmark recorded at 2026-10-12T22:13:26.196Z UTC.

Phase 4 validated fresh model inference, the financial engine, browser request mapping and live Groq interpretation. Phase 5 connected the pinned TradingAgents bull/bear/research-manager nodes to the existing metered Groq service and manually triggered a complete live review.

## Real forecasting outputs

| Scenario | Market | Models | Completed candles | Forecast steps | Measured inference |
|---|---|---:|---:|---:|---:|
| Single | ETHUSDT, 5m | Kronos Mini | 80 | 8 | 1.61 s |
| Batch | ETHUSDT and BTCUSDT, 5m | All six per market | 80 each | 8 each | 17.52 s total |

All six models ran real inference: Kronos Mini, Small, Base, Chronos-2, TimesFM 2.5 and FinCast. Runs used CPU and one sample, with installed/cached model assets. These timings describe these runs, not average or cold-install performance.

The standalone validator checked all thirteen model outputs across the three snapshots: finite positive forecast closes, horizon lengths, forecast timestamps, selected model identities and Python change/direction calculations. The three snapshots' candle histories were completed and their Python metrics matched the forecast inputs.

A verified input issue was corrected: Binance's currently forming candle is excluded by its close timestamp; one extra row is requested to retain the desired completed lookback. Forecasting algorithms were preserved. The browser test reuses the fresh real API outputs to avoid repeating model loading, then makes real analysis requests from the interface.

## Live analysis benchmark

| Analysis | Provider calls | Metered tokens | Elapsed |
|---|---:|---:|---:|
| Groq interpretation baseline | 1 | 1,559 | Not retained |
| TradingAgents research review | 3 | 6,178 | 3.25 s |

The successful review used about 3.96 times the baseline tokens. This is one measured snapshot, not a cost/latency average. The baseline was reused for the final review benchmark to avoid another provider call. Usage includes actual billable tokens reported through the existing local recorder; the full-run conservative reservation was 34,086 tokens.

Every returned evidence ID was present in the Python evidence. The review's technical and forecast metrics exactly matched the independent metrics endpoint. No numeric claim was substituted by a language model. The browser contacted the local backend, never the Groq provider directly, and did not send private paths or credentials.

Development validation caught three failure cases: an invalid first research response, unsupported schema constraints, and an overlong full-bucket pacing calculation after two successful turns. Each attempt was recorded; failures did not automatically retry. The final implementation uses supported enum constraints, shorter snapshot prompts and deficit-based pacing, and the complete live run passed.

## Verification results

- 126/126 backend tests passed.
- TypeScript, lint and production build passed.
- Desktop (1440 px) and mobile (390 px) interaction/layout checks passed, with no browser execution errors.
- No AI call occurs during initial load or forecast rendering. Duplicate clicks issue one review request. All six selected forecasts are sent; batch mode sends the selected market. A changed result clears findings and late responses cannot populate another result.
- Fixed frontend errors do not echo arbitrary provider messages. The mobile candlestick toolbar was corrected to wrap instead of causing horizontal page overflow.
- The tracker source and private installed copy remain synchronized. Usage logs and alert state were preserved.

At benchmark completion, locally recorded UTC-day usage was **10.62%** (21,233 tokens and 24 request attempts). Pending milestones were [5, 10]; notification acknowledgment remains with the existing automation. These are historical benchmark readings.

The checks validate integration, source identity, grounding and quota behavior. Forecast accuracy, profitability and historical strategy performance require Phase 6 backtesting and paper trading. Trade execution remains disabled.

## Reusing the validator

`scripts/validate_analysis_snapshot.py` accepts a real single-result JSON and a real batch-result JSON, reads the local metrics endpoint and writes a bounded validation report. It makes no Groq calls.

```sh
python scripts/validate_analysis_snapshot.py --single-file result.json --batch-file batch.json --output validation.json
```

The TradingAgents implementation and pinned upstream/license boundary are documented in `docs/trading-agents.md`.

## Subsequent independent dashboard update

The forecast-bound panel used in the historical benchmark above has been replaced by `/ai-analysis`. The current shared service pins all providers to GPT-OSS-120B and switches immediately rather than pacing for refill. Three research turns remain bounded, with at most nine attempts across the three providers. See `docs/ai-providers.md` for the current implementation and validation boundary.
