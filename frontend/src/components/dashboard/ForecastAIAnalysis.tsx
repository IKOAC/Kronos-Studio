"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { analyzeWithGroq, analyzeWithTradingAgents, getGroqUsage } from "@/lib/api/groqAnalysis";
import type { GroqAnalysisResponse, GroqQuota, TradingAgentsResponse } from "@/schemas/groqAnalysisSchema";
import type { PricePredictionResponse } from "@/schemas/predictionSchema";
import AnalysisResults from "./AnalysisResults";

type AnalysisMode = "single" | "agents";

export default function ForecastAIAnalysis({ result }: { result: PricePredictionResponse }) {
  const [analysis, setAnalysis] = useState<GroqAnalysisResponse | TradingAgentsResponse | null>(null);
  const [quota, setQuota] = useState<GroqQuota | null>(null);
  const [quotaError, setQuotaError] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<AnalysisMode | null>(null);
  const request = useRef<AbortController | null>(null);
  const status = useRef<AbortController | null>(null);

  const refreshQuota = useCallback(async () => {
    status.current?.abort();
    const controller = new AbortController();
    status.current = controller;
    try {
      const next = await getGroqUsage(controller.signal);
      if (!controller.signal.aborted) {
        setQuota(next);
        setQuotaError(false);
      }
    } catch {
      if (!controller.signal.aborted) {
        setQuota(null);
        setQuotaError(true);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    status.current = controller;
    getGroqUsage(controller.signal).then((next) => {
      if (!controller.signal.aborted) { setQuota(next); setQuotaError(false); }
    }).catch(() => {
      if (!controller.signal.aborted) { setQuota(null); setQuotaError(true); }
    });
    return () => {
      request.current?.abort();
      status.current?.abort();
    };
  }, []);

  const exhausted = quota?.usage_percent != null && quota.usage_percent >= quota.cap_percent;

  async function analyze(mode: AnalysisMode) {
    if (request.current || quotaError || exhausted) return;
    const controller = new AbortController();
    request.current = controller;
    setRunning(mode);
    setAnalysis(null);
    setError(null);
    try {
      const response = mode === "single"
        ? await analyzeWithGroq(result, controller.signal)
        : await analyzeWithTradingAgents(result, controller.signal);
      if (!controller.signal.aborted) setAnalysis(response);
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(cause instanceof Error ? cause.message : "Forecast analysis failed.");
      }
    } finally {
      if (!controller.signal.aborted) {
        request.current = null;
        setRunning(null);
        await refreshQuota();
      }
    }
  }

  const forecastCount = result.model_comparisons?.length || 1;
  return (
    <section className="space-y-4 border border-border bg-card p-5 sm:p-7" aria-label="Forecast AI analysis">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <span className="terminal-kicker">/ OPTIONAL FORECAST RESEARCH</span>
          <h3 className="mt-2 text-lg font-semibold">Analyze selected forecast</h3>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-muted-foreground">
            Manual requests only. Uses {forecastCount} forecast model{forecastCount === 1 ? "" : "s"} and the selected result&apos;s
            candle history. Python calculates the metrics; Groq interprets the evidence.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" disabled={!!running || quotaError || exhausted} onClick={() => void analyze("single")}>
            {running === "single" ? "Analyzing…" : "Analyze with Groq"}
          </Button>
          <Button type="button" variant="outline" disabled={!!running || quotaError || exhausted} onClick={() => void analyze("agents")}>
            {running === "agents" ? "Reviewing…" : "TradingAgents review"}
          </Button>
        </div>
      </div>
      <p className="terminal-mono text-[11px] text-muted-foreground" role="status">
        {quotaError
          ? "Usage tracker unavailable. Analysis is disabled until tracking is restored."
          : quota
            ? `Groq: ${quota.tokens_observed.toLocaleString()} recorded tokens · ${quota.usage_percent?.toFixed(2) ?? "Unknown"}% usage · ${quota.cap_percent}% daily ceiling`
            : "Checking local Groq usage tracker…"}
        {exhausted ? " Daily ceiling reached." : ""}
      </p>
      {running && <p className="text-xs text-muted-foreground">Research is in progress; the current request may be billed even if this view is closed.</p>}
      {error && <p role="alert" className="border border-destructive/40 p-3 text-sm text-destructive">{error}</p>}
      {analysis && <AnalysisResults analysis={analysis} />}
    </section>
  );
}
