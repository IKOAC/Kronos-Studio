import { z } from "zod";
import type { PricePredictionResponse } from "@/schemas/predictionSchema";

const finite = z.number().finite();

const TechnicalMetricsSchema = z.object({
  candles: z.number().int(),
  last_close: finite,
  sma_20: finite.nullable(),
  sma_50: finite.nullable(),
  sma_200: finite.nullable(),
  ema_12: finite.nullable(),
  ema_20: finite.nullable(),
  ema_26: finite.nullable(),
  ema_50: finite.nullable(),
  rsi_14: finite.nullable(),
  macd_12_26: finite.nullable(),
  macd_signal_9: finite.nullable(),
  macd_histogram: finite.nullable(),
  atr_14: finite.nullable(),
  bollinger_middle_20: finite.nullable(),
  bollinger_upper_20: finite.nullable(),
  bollinger_lower_20: finite.nullable(),
  volume_ratio_20: finite.nullable()
});

const ForecastMetricsSchema = z.object({
  models: z.array(z.object({
    model_name: z.string(),
    final_close: finite,
    change_pct: finite,
    direction: z.enum(["up", "down", "flat"])
  })),
  direction_counts: z.record(z.string(), z.number().int()),
  majority_direction: z.enum(["up", "down", "flat"]).nullable(),
  agreement_pct: finite.nullable(),
  mean_change_pct: finite,
  median_change_pct: finite,
  dispersion_std_pct: finite,
  change_range_pct: finite
});

const TradeMetricsSchema = z.object({
  side: z.enum(["long", "short"]),
  assumed_entry_fill: finite,
  assumed_stop_fill: finite,
  assumed_target_fill: finite,
  loss_per_unit_including_costs: finite,
  profit_per_unit_after_costs: finite,
  net_reward_to_risk: finite,
  break_even_win_rate_pct: finite.nullable(),
  risk_budget: finite,
  exposure_budget: finite,
  quantity: finite,
  planned_stop_loss: finite,
  planned_target_profit: finite,
  required_entry_notional_and_fee: finite,
  stop_loss_guaranteed: z.boolean()
});

const QuotaSchema = z.object({
  day_utc: z.string(),
  token_limit_assumed: z.number().positive(),
  tokens_observed: z.number().nonnegative(),
  token_percent_observed: finite,
  requests_limit: z.number().positive(),
  requests_used: z.number().nonnegative(),
  requests_percent_used: finite,
  usage_percent: finite,
  cap_percent: finite,
  pending_5pct_alerts: z.array(z.number().int()),
  token_tracking_scope: z.literal("locally_recorded")
});

export const GroqAnalysisResponseSchema = z.object({
  symbol: z.string(),
  interval: z.string(),
  provider: z.literal("groq"),
  model: z.literal("openai/gpt-oss-120b"),
  metrics: z.object({
    technical: TechnicalMetricsSchema,
    forecast: ForecastMetricsSchema.nullable(),
    trade: TradeMetricsSchema.nullable()
  }),
  findings: z.object({
    summary: z.string(),
    supporting_evidence_ids: z.array(z.string()),
    conflicting_evidence_ids: z.array(z.string()),
    limitations: z.array(z.string())
  }),
  forecast_consensus: z.enum(["up", "down", "flat", "mixed", "insufficient"]),
  quota: QuotaSchema
});

export const GroqQuotaSchema = QuotaSchema;
export type GroqAnalysisResponse = z.infer<typeof GroqAnalysisResponseSchema>;
export type GroqQuota = z.infer<typeof GroqQuotaSchema>;

// The backend only receives numeric candle values and final closing forecasts.
// No arbitrary text, API keys, files, or stored credentials leave the browser.
export function buildGroqPayload(result: PricePredictionResponse) {
  const comparisons = result.model_comparisons;
  const forecasts = comparisons.length > 0
    ? comparisons.map((item) => ({
        model_name: item.model_name,
        final_close: item.prediction.at(-1)?.close
      }))
    : [{
        model_name: result.request.model_name,
        final_close: result.prediction.at(-1)?.close
      }];
  if (forecasts.some((forecast) => forecast.final_close === undefined)) {
    throw new Error("Forecast output is missing a final close.");
  }
  const symbol = result.request.symbol;
  if (!symbol || !/^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,31}$/.test(symbol)) {
    throw new Error("A valid market symbol is required for AI analysis.");
  }
  if (!/^[0-9]{1,3}[smhdwM]$/.test(result.request.interval)) {
    throw new Error("The selected interval cannot be analyzed.");
  }
  const history = result.history.map((row) => ({
    timestamps: row.timestamps,
    open: row.open,
    high: row.high,
    low: row.low,
    close: row.close,
    volume: row.volume
  }));
  if (history.length < 2) {
    throw new Error("AI analysis requires at least two completed market candles.");
  }

  return {
    symbol,
    interval: result.request.interval,
    history,
    forecasts,
  };
}
