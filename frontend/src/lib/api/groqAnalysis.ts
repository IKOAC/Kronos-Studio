import { endpoint } from "@/utils/handleAPI";
import {
  buildGroqPayload, GroqAnalysisResponseSchema, GroqQuotaSchema, TradingAgentsResponseSchema, AIProvidersSchema,
} from "@/schemas/groqAnalysisSchema";
import type { MarketAnalysisInput } from "@/schemas/groqAnalysisSchema";
import type { PricePredictionResponse } from "@/schemas/predictionSchema";

const messages: Record<string, string> = {
  ALL_PROVIDERS_UNAVAILABLE: "All configured OSS-120B providers are unavailable or exhausted. Check provider status below.",
  PROVIDER_NOT_CONFIGURED: "The provider connection is not configured in the backend.",
  MODEL_NOT_ALLOWED: "The provider did not return the required OSS-120B model.",
  MARKET_DATA_UNAVAILABLE: "Completed market data could not be loaded. Check the source, symbol and history period.",
  GROQ_DAILY_CAP: "The analysis would exceed the daily usage ceiling.",
  GROQ_RATE_LIMITED: "The configured providers are rate-limiting requests. Try again later.",
  GROQ_NOT_CONFIGURED: "The backend Groq credential is not configured.",
  TRACKER_UNAVAILABLE: "Quota tracking is unavailable. Analysis is blocked.",
  GROQ_INVALID_OUTPUT: "The provider returned an unsupported analysis. Usage was recorded.",
  GROQ_TRANSPORT_ERROR: "Groq did not return a usable response. The attempt was recorded.",
  GROQ_UPSTREAM_ERROR: "The provider could not complete the analysis.",
  AGENT_RUN_LIMIT: "The TradingAgents review reached its request limit.",
  AGENT_METRICS_CHANGED: "The research evidence failed its integrity check.",
  ANALYSIS_TOO_LARGE: "The analysis snapshot is too large.",
};

async function readResponse<T>(response: Response, schema: { parse: (data: unknown) => T }) {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const code = data?.detail?.code;
    // Only display known messages, never arbitrary provider bodies or validation inputs.
    throw new Error(messages[code] ?? (response.status === 422
      ? "Market data could not be validated for analysis."
      : response.status === 403
        ? "AI analysis requires the local workspace at port 3000."
        : "The analysis service is unavailable."));
  }
  try {
    return schema.parse(data);
  } catch {
    throw new Error("The analysis service returned an invalid response.");
  }
}

export async function getGroqUsage(signal?: AbortSignal) {
  const response = await fetch(endpoint("/analysis/groq/usage"), { cache: "no-store", signal });
  return readResponse(response, GroqQuotaSchema);
}

async function requestAnalysis<T extends { symbol: string; interval: string }>(
  result: PricePredictionResponse, route: string, schema: { parse: (data: unknown) => T }, signal?: AbortSignal,
) {
  const body = buildGroqPayload(result);
  const response = await fetch(endpoint(route), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    signal,
  });
  const analysis = await readResponse(response, schema);
  if (analysis.symbol !== body.symbol || analysis.interval !== body.interval) {
    throw new Error("The analysis does not match the selected market.");
  }
  return analysis;
}

export function analyzeWithGroq(result: PricePredictionResponse, signal?: AbortSignal) {
  return requestAnalysis(result, "/analysis/groq", GroqAnalysisResponseSchema, signal);
}

export function analyzeWithTradingAgents(result: PricePredictionResponse, signal?: AbortSignal) {
  return requestAnalysis(result, "/analysis/trading-agents", TradingAgentsResponseSchema, signal);
}

export async function getAIProviders(signal?: AbortSignal) {
  const response = await fetch(endpoint("/analysis/providers"), { cache: "no-store", signal });
  return readResponse(response, AIProvidersSchema);
}

export async function analyzeMarket(input: MarketAnalysisInput, signal?: AbortSignal) {
  const body = { ...input, symbol: input.symbol.trim().toUpperCase() };
  const response = await fetch(endpoint("/analysis/market"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body), cache: "no-store", signal,
  });
  const schema = input.mode === "agents" ? TradingAgentsResponseSchema : GroqAnalysisResponseSchema;
  const result = await readResponse(response, schema);
  if (result.symbol !== body.symbol || result.interval !== body.interval) throw new Error("The analysis does not match the selected market.");
  return result;
}
