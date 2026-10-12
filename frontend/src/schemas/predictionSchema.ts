import { z } from "zod";

export const DataSourceEnum = z.enum(["binance", "yfinance", "local"]);
export const ModelNameEnum = z.enum(["kronos-mini", "kronos-small", "kronos-base", "chronos-2", "timesfm-2.5", "fincast"]);
export type ModelName = z.infer<typeof ModelNameEnum>;
export const DeviceEnum = z.enum(["cpu", "cuda:0", "mps"]);

export const PricePredictionRequestSchema = z.object({
  data_source: DataSourceEnum.default("binance"),
  symbol: z.string().nullable().default("ETHUSDT"),
  local_path: z.string().nullable().optional(),
  period: z.string().default("30d"),
  interval: z.string().default("1h"),
  lookback: z.number().int().min(2).default(400),
  pred_len: z.number().int().min(1).default(120),
  limit: z.number().int().min(1).nullable().default(400),
  model_name: ModelNameEnum.default("kronos-mini"),
  selected_models: z.array(ModelNameEnum).min(1).max(6).default(["kronos-mini", "kronos-small", "kronos-base"]),
  model_ids: z.partialRecord(ModelNameEnum, z.string().trim().regex(/^[\w.-]+\/[\w.-]+$/, "Use owner/model as the Hugging Face ID")).default({}),
  device: DeviceEnum.default("cpu"),
  temperature: z.number().gt(0).default(1),
  top_k: z.number().int().min(0).default(0),
  top_p: z.number().gt(0).lte(1).default(0.9),
  sample_count: z.number().int().min(1).default(1),
  verbose: z.boolean().default(false)
});

export const PricePredictionBatchRequestSchema = z.array(PricePredictionRequestSchema);

export const AvailableModelSchema = z.object({
  name: z.string(),
  model_id: z.string(),
  tokenizer_id: z.string().nullable().default(null),
  context_length: z.number().int(),
  params: z.string(),
  description: z.string(),
  adapter: z.string().default("kronos"),
  output_type: z.enum(["candles", "close"]).default("candles"),
  devices: z.array(DeviceEnum).default(["cpu", "cuda:0", "mps"]),
  max_horizon: z.number().int().nullable().default(null)
});

export const CandleRecordSchema = z.object({
  timestamps: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number(),
  amount: z.number()
});

export const ModelComparisonSchema = z.object({
  model_name: ModelNameEnum,
  model: AvailableModelSchema,
  prediction: z.array(CandleRecordSchema.extend({
    open: z.number().nullable().default(null), high: z.number().nullable().default(null),
    low: z.number().nullable().default(null), volume: z.number().nullable().default(null),
    amount: z.number().nullable().default(null)
  })),
  direction: z.enum(["up", "down", "flat"]),
  predicted_change_pct: z.number(),
  confidence_score: z.number().min(0).max(100),
  confidence_label: z.enum(["Low agreement", "Moderate agreement", "High agreement", "Not comparable"]),
  sample_count: z.number().int().min(1),
  direction_counts: z.object({
    up: z.number().int(),
    down: z.number().int(),
    flat: z.number().int()
  })
});

export const PredictionOptionsResponseSchema = z.object({
  data_sources: z.array(DataSourceEnum),
  models: z.partialRecord(ModelNameEnum, AvailableModelSchema),
  devices: z.array(DeviceEnum),
  common_intervals: z.array(z.string()),
  common_periods: z.array(z.string()),
  defaults: PricePredictionRequestSchema
});

export const UploadedDataFileResponseSchema = z.object({
  filename: z.string(),
  stored_path: z.string(),
  size_bytes: z.number().int().nonnegative(),
  row_count: z.number().int().nonnegative(),
  columns: z.array(z.string())
});

export const PricePredictionResponseSchema = z.object({
  request: PricePredictionRequestSchema,
  model: AvailableModelSchema,
  lookback_start_timestamp: z.string(),
  lookback_end_timestamp: z.string(),
  prediction_start_timestamp: z.string(),
  history: z.array(CandleRecordSchema),
  future_timestamps: z.array(z.string()),
  prediction: ModelComparisonSchema.shape.prediction,
  model_comparisons: z.array(ModelComparisonSchema).default([])
});

export const PricePredictionBatchResponseSchema = z.array(PricePredictionResponseSchema);

export type PricePredictionRequest = z.infer<typeof PricePredictionRequestSchema>;
export type PricePredictionResponse = z.infer<typeof PricePredictionResponseSchema>;
export type ModelComparison = z.infer<typeof ModelComparisonSchema>;
export type PricePredictionBatchRequest = z.infer<typeof PricePredictionBatchRequestSchema>;
export type PricePredictionBatchResponse = z.infer<typeof PricePredictionBatchResponseSchema>;
export type UploadedDataFileResponse = z.infer<typeof UploadedDataFileResponseSchema>;

export type PredictionOptionsResponse = z.infer<typeof PredictionOptionsResponseSchema>;
