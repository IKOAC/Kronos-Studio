import { endpoint } from "@/utils/handleAPI";
import {
  buildGroqPayload, GroqAnalysisResponseSchema, GroqQuotaSchema,
} from "@/schemas/groqAnalysisSchema";
import type { PricePredictionResponse } from "@/schemas/predictionSchema";

const messages: Record<string, string> = {
  GROQ_DAILY_CAP: "The analysis would exceed the daily usage ceiling.",
  GROQ_RATE_LIMITED: "Groq is rate-limiting requests. Try again later.",
  GROQ_NOT_CONFIGURED: "The backend Groq credential is not configured.",
  TRACKER_UNAVAILABLE: "Quota tracking is unavailable. Analysis is blocked.",
  GROQ_INVALID_OUTPUT: "Groq returned an unsupported analysis. Usage was recorded.",
  GROQ_TRANSPORT_ERROR: "Groq did not return a usable response. The attempt was recorded.",
  GROQ_UPSTREAM_ERROR: "Groq could not complete the analysis.",
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

export async function analyzeWithGroq(result: PricePredictionResponse, signal?: AbortSignal) {
  const body = buildGroqPayload(result);
  const response = await fetch(endpoint("/analysis/groq"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    signal,
  });
  const analysis = await readResponse(response, GroqAnalysisResponseSchema);
  if (analysis.symbol !== body.symbol || analysis.interval !== body.interval) {
    throw new Error("The analysis does not match the selected market.");
  }
  return analysis;
}
