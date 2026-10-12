# Financial calculation engine

Backend: `server/services/financial_analysis/engine.py`. JSON endpoint: `POST /api/analysis/metrics`.

- Pure, read-only calculations. No market fetch, prediction run, Groq call, orders, or saved trades.
- Receives **completed** OHLCV candles in strictly increasing timestamp order.
- Input: `history` (2–10,000 candles), optional `forecasts` (up to 20 named final-horizon closing prices), optional `trade`.
- Input price levels must be positive finite numbers; candles must satisfy `low <= open,close <= high`. Non-monotonic timestamps, duplicate model IDs, or invalid trade geometry return HTTP 422.
- Returns a `technical` object and optional `forecast` and `trade` objects. No performance metric is a prediction of correctness.

## Technical metrics

Values are evaluated at the last supplied candle. Insufficient lookback returns JSON `null`, never a synthetic zero.

| Metric | Definition | Minimum closed candles |
| --- | --- | ---: |
| SMA 20 / 50 / 200 | Arithmetic mean of final N closing prices | 20 / 50 / 200 |
| EMA 12 / 20 / 26 / 50 | Pandas `ewm(span=N, adjust=False)` | 12 / 20 / 26 / 50 |
| RSI 14 | Wilder smoothing, seeded with mean of first 14 gains and losses; all-flat is 50 | 15 |
| MACD (12,26) | EMA(12) - EMA(26) | 26 |
| MACD signal 9 | EMA(9) of MACD with 9 valid MACD observations | 34 |
| MACD histogram | MACD - signal | 34 |
| ATR 14 | Wilder smoothing of true range, seeded with first 14 true ranges | 14 |
| Bollinger 20 | SMA(20) ± 2 × population standard deviation of 20 closes | 20 |
| Volume ratio 20 | Latest volume / mean volume of last 20 bars; null if mean is zero | 20 |

ATR uses the first candle's `high-low` as its first true range, since there is no prior close. The caller must ensure candles are closed; this endpoint does not inspect a live exchange clock.

## Forecast comparisons

Provide one final closing price per model with `model_name` and `final_close`. Change % is `100 × (predicted_close / last_actual_close − 1)`. Direction is **up** above +0.1%, **down** below -0.1%, otherwise **flat**, matching the existing prediction service threshold.

The response includes per-model changes, directional counts, unweighted mean and median changes, population standard deviation and full range of changes, plus the modal direction and agreement percentage. With one model, agreement is null. Tied modal directions have no majority. **Agreement is not a probability or calibrated model confidence.** These results are not historical forecast accuracy.

## Hypothetical trade calculations

Mandatory trade fields: `side` (`long` or `short`), `entry`, `stop`, `target`, `account_equity`, and `risk_percent`. Optional fields default to `fee_bps=0`, `slippage_bps=0`, `quantity_step=0.000001` and `max_exposure_percent=100`.

- Geometry: long requires `stop < entry < target`; short requires `target < entry < stop`.
- Entry and exit slippage are adverse in both directions. Long entry = entry × (1 + slippage); long exits = exit × (1 − slippage). Short entry = entry × (1 − slippage); short exits = exit × (1 + slippage).
- Fee on each side = filled execution price × `fee_bps / 10000`.
- Long stop loss per unit = entry fill − stop fill + entry and stop fees. Short stop loss per unit = stop fill − entry fill + fees.
- Net target reward similarly subtracts both target and entry fees. Net reward-to-risk = net target reward / estimated stop loss. Break-even win percentage is omitted when the net target reward is non-positive.
- Risk budget = account equity × risk %. Exposure budget = account equity × max exposure %. Quantity is the minimum of risk-budget / estimated loss per unit and exposure-budget / (entry fill × (1 + fee)), **rounded down** to the exchange quantity step.
- The conservative exposure budget is not a margin or short-borrow calculation. Leverage, financing rates, borrow availability, exchange minimum orders, changing liquidity, taxes, liquidation, and execution guarantees are **not** modeled.
- Stop losses can execute worse than assumed. Reported planned stop losses are **not guaranteed maxima**.

All trade monetary arithmetic uses Python `Decimal`; the API serializes numbers as JSON floats.

## Example

```json
{
  "history": [
    {"timestamps": "2026-01-01T00:00:00", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10},
    {"timestamps": "2026-01-01T01:00:00", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 12}
  ],
  "forecasts": [{"model_name": "kronos-mini", "final_close": 102}],
  "trade": {
    "side": "long", "entry": 100, "stop": 97, "target": 106,
    "account_equity": 1000, "risk_percent": 1, "quantity_step": 0.01
  }
}
```

For the complete RSI/MACD/Bollinger outputs, send at least 34 closed candles; for SMA200, send at least 200.

## Test and benchmark

```sh
cd server
uv run --no-sync pytest -q
```

The module uses NumPy/Pandas already installed by the server. No additional packages or API keys are required. Benchmark figures depend on platform, input shape, and hardware and are not a remote API latency guarantee.

Future AI analysis should call this module rather than computing these values in an LLM. The Groq quota tracker remains separate and unchanged.
