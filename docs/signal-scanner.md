# Signal scanner

Open `/signal-scanner` from the sidebar or AI analysis page. **Start scan** performs one bounded scan; it does not schedule recurring work or place orders. The default is at most two reviews on 15-minute candles. One-hour candles and one to three reviews are also available. **Stop scan** cancels later stages; an in-flight provider request may finish and remains metered.

## Market selection

The fixed universe is BTC, ETH, SOL, BNB, XRP, ADA, LINK and AVAX quoted in USDT. Binance public 24-hour tickers and current bid/ask quotes must report at least 50 million USDT of quote volume and a spread no greater than 0.08%. These are liquidity filters, not guarantees of price stability.

The scanner shuffles eligible pairs, screens at most four, ranks them by technical checks passed, and reviews the strongest requested number. Random ordering breaks tied scores. It loads 200 consecutive completed candles per pair. Missing, gapped, nonfinite or stale evidence cannot produce a setup.

## Setup rules

The direction follows EMA twenty relative to EMA fifty. Every check must pass:

- Price and both averages align with the proposed direction.
- RSI is 55–68 for a long or 32–45 for a short, with matching MACD-histogram direction.
- Last-candle volume is at least 1.10 times its twenty-candle average.
- ATR is 0.10–2.50% of closing price.
- The entry trigger is within one ATR of closing price.
- Price is within two ATR of EMA twenty.

The conditional entry is beyond the most recent ten-candle high/low by 0.05 ATR. The stop is 1.5 ATR from entry. Target arithmetic solves for 2:1 net reward/risk using assumed fees of ten basis points and adverse slippage of five basis points per side. Prices are research levels; they are not exchange tick-size-rounded orders, and short-instrument availability is not checked. These strategy thresholds have no measured win rate or backtested performance claim.

## Actual agent discussion

The scanner invokes the existing TradingAgents bull, bear and research-manager nodes in sequence. Bear receives the bull's response; the manager receives both. Events show the role currently executing and publish each validated review when it completes. No invented messages or internal chain-of-thought are shown.

The scanner adds a typed `setup_verdict` (`supports`, `rejects`, `unclear`) to the existing bounded findings. Reviewers assess code-calculated levels and cannot replace them. A signal requires all six checks and three supporting verdicts. Before publishing, the scanner rechecks current liquidity and confirms that price has not already reached the trigger. The snapshot expires at the next candle close; an expired snapshot is rejected and the browser marks an expired report visibly. The scan stops at its first qualifying signal, or ends with no qualifying setup.

## Streaming and limits

`POST /api/analysis/scanner/stream` accepts only `interval` and `pairs` and returns newline-delimited JSON. It retains the local-client and browser-origin guard. A process-wide scanner lock permits one active scanner, including shutdown of a cancelled run. All model calls use Groq's existing private quota tracker, bounded refill waits, and retry limits. A provider error stops the scan and retains completed reviews in the browser. If more than one pair has been reviewed, the discussion selector allows earlier pairs to be inspected without losing the current results. A single scan can consume multiple three-turn reviews; quota limits may stop it before all pairs finish.

Regression tests cover setup arithmetic, stale and gapped data, weak liquidity, failed technical checks, reviewer disagreement, a reached entry, cancellation, provider errors, concurrency, actual TradingAgents prompt flow, and the frontend/backend streaming contract.

Sources for the data and indicator definitions: [Binance public market-data API](https://developers.binance.com/en/docs/products/spot/rest-api), [Fidelity ATR guide](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr). The setup thresholds above are product rules, not recommendations from these sources.
