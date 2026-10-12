"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { analyzeWithGroq, analyzeWithTradingAgents, getGroqUsage } from "@/lib/api/groqAnalysis";
import type { GroqAnalysisResponse, GroqQuota, TradingAgentsResponse } from "@/schemas/groqAnalysisSchema";
import type { PricePredictionResponse } from "@/schemas/predictionSchema";

const format = (value: number | null | undefined, suffix = "") =>
  value == null ? "—" : `${value.toLocaleString(undefined, { maximumFractionDigits: 4 })}${suffix}`;

function Evidence({ ids, analysis }: { ids: string[]; analysis: GroqAnalysisResponse }) {
  const facts: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(analysis.metrics.technical)) facts[`technical.${key}`] = value;
  if (analysis.metrics.forecast) {
    for (const [key, value] of Object.entries(analysis.metrics.forecast)) facts[`forecast.${key}`] = value;
    for (const model of analysis.metrics.forecast.models) {
      facts[`forecast.model.${model.model_name}`] = { change_pct: model.change_pct, direction: model.direction };
    }
  }
  if (analysis.metrics.trade) {
    for (const [key, value] of Object.entries(analysis.metrics.trade)) facts[`trade.${key}`] = value;
  }
  if (!ids.length) return <p className="text-xs text-muted-foreground">None cited.</p>;
  return <ul className="space-y-2">{ids.map((id) => (
    <li key={id} className="break-words text-xs">
      <span className="text-muted-foreground">{id.replaceAll("_", " ")}</span>
      <span className="terminal-mono ml-2">{typeof facts[id] === "number" ? format(facts[id] as number) : JSON.stringify(facts[id]) ?? "Unavailable"}</span>
    </li>
  ))}</ul>;
}

function AnalysisSession({ result }: { result: PricePredictionResponse }) {
  const [analysis, setAnalysis] = useState<GroqAnalysisResponse | TradingAgentsResponse | null>(null);
  const [quota, setQuota] = useState<GroqQuota | null>(null);
  const [usageError, setUsageError] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<"groq" | "agents" | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    // This reads the local log only; it never calls Groq.
    getGroqUsage(controller.signal).then((usage) => setQuota((current) => current ?? usage)).catch(() => {
      if (!controller.signal.aborted) setUsageError(true);
    });
    return () => {
      controller.abort();
      activeRequest.current?.abort();
    };
  }, []);

  async function analyze(mode: "groq" | "agents") {
    if (activeRequest.current) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(mode);
    setError(null);
    setAnalysis(null);
    try {
      const response = await (mode === "agents" ? analyzeWithTradingAgents : analyzeWithGroq)(result, controller.signal);
      if (!controller.signal.aborted) {
        setAnalysis(response);
        setQuota(response.quota);
        setUsageError(false);
      }
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(cause instanceof TypeError ? "Cannot reach the local analysis backend." : cause instanceof Error ? cause.message : "Analysis failed.");
        // Failed provider calls are metered too. Refresh the log without retrying analysis.
        try {
          const usage = await getGroqUsage(controller.signal);
          if (!controller.signal.aborted) { setQuota(usage); setUsageError(false); }
        } catch { if (!controller.signal.aborted) setUsageError(true); }
      }
    } finally {
      if (!controller.signal.aborted) setLoading(null);
      activeRequest.current = null;
    }
  }

  const technical = analysis?.metrics.technical;
  const forecast = analysis?.metrics.forecast;
  return (
    <section id="ai-analysis" className="min-w-0 scroll-mt-6 border-t border-border pt-6" aria-labelledby="analysis-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 id="analysis-heading" className="text-lg font-bold tracking-tight">AI analysis</h4>
          <p className="mt-1 text-xs text-muted-foreground">{result.request.symbol || "Local market"} · {result.request.interval} · Python metrics / Groq interpretation</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => analyze("groq")} disabled={loading !== null || (quota !== null && quota.usage_percent >= quota.cap_percent)}>
            {loading === "groq" ? "Analyzing…" : "Analyze with Groq"}
          </Button>
          <Button type="button" variant="outline" onClick={() => analyze("agents")} disabled={loading !== null || (quota !== null && quota.usage_percent >= quota.cap_percent)}>
            {loading === "agents" ? "Reviewing…" : "Run TradingAgents review"}
          </Button>
        </div>
      </div>
      <p className="terminal-mono mt-3 break-words text-[11px] text-muted-foreground" aria-live="polite">
        {quota ? `Recorded usage: ${quota.usage_percent.toFixed(2)}% · ceiling ${quota.cap_percent}% · ${quota.tokens_observed.toLocaleString()} tokens / ${quota.requests_used.toLocaleString()} requests · UTC ${quota.day_utc}` : "Recorded usage unavailable."}
        {usageError && " Usage could not be refreshed."}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">Runs only on click. TradingAgents reviews the evidence in three calls. Token totals cover locally recorded calls.</p>
      {loading && <p className="mt-4 text-sm text-muted-foreground" role="status">{loading === "agents" ? "Reviewing bullish evidence, bearish evidence, and the combined assessment…" : "Calculating metrics and interpreting the selected forecast…"}</p>}
      {error && <p className="mt-4 text-sm text-destructive" role="alert">{error}</p>}
      {analysis && technical && (
        <div className="mt-5 space-y-5">
          <div aria-live="polite">
            <p className="terminal-kicker">{"agents" in analysis ? "TRADINGAGENTS ASSESSMENT" : "GROQ ASSESSMENT"}</p>
            <p className="mt-2 text-sm leading-relaxed">{analysis.findings.summary}</p>
          </div>
          {"agents" in analysis && (
            <div className="space-y-3">
              <p className="terminal-mono text-[11px] text-muted-foreground">
                {analysis.run_stats.requests_used} calls · {analysis.run_stats.tokens_used.toLocaleString()} tokens · {(analysis.run_stats.elapsed_ms / 1000).toFixed(2)}s
              </p>
              {analysis.agents.filter((agent) => agent.role !== "research_manager").map((agent) => (
                <details key={agent.role} className="border border-border p-3">
                  <summary className="cursor-pointer text-xs font-semibold">{agent.role === "bull" ? "Bull researcher" : "Bear researcher"}</summary>
                  <p className="mt-3 text-sm leading-relaxed">{agent.findings.summary}</p>
                  <div className="mt-3 space-y-3">
                    <div><h5 className="mb-2 text-xs font-semibold">Supporting evidence</h5><Evidence ids={agent.findings.supporting_evidence_ids} analysis={analysis} /></div>
                    <div><h5 className="mb-2 text-xs font-semibold">Conflicting evidence</h5><Evidence ids={agent.findings.conflicting_evidence_ids} analysis={analysis} /></div>
                    {agent.findings.limitations.length > 0 && <ul className="list-inside list-disc text-xs text-muted-foreground">{agent.findings.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}
                  </div>
                </details>
              ))}
            </div>
          )}
          <dl className="grid grid-cols-2 gap-4 border-y border-border py-4 sm:grid-cols-3">
            {[
              ["RSI (14)", format(technical.rsi_14)],
              ["MACD (12/26)", format(technical.macd_12_26)],
              ["MACD signal (9)", format(technical.macd_signal_9)],
              ["EMA (20)", format(technical.ema_20)],
              ["EMA (50)", format(technical.ema_50)],
              ["ATR (14)", format(technical.atr_14)],
              ["Model agreement", format(forecast?.agreement_pct, "%")],
              ["Forecast dispersion", format(forecast?.dispersion_std_pct, " pp")],
              ["Forecast consensus", analysis.forecast_consensus],
            ].map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-[11px] text-muted-foreground">{label}</dt><dd className="terminal-mono mt-1 break-words text-sm">{value}</dd></div>)}
          </dl>
          <p className="text-xs text-muted-foreground">Metrics calculated by Python. — indicates insufficient history or comparable models. Agreement measures direction, not forecast accuracy.</p>
          <div className="grid gap-5 sm:grid-cols-2">
            <div><h5 className="mb-2 text-xs font-semibold">Supporting evidence</h5><Evidence ids={analysis.findings.supporting_evidence_ids} analysis={analysis} /></div>
            <div><h5 className="mb-2 text-xs font-semibold">Conflicting evidence</h5><Evidence ids={analysis.findings.conflicting_evidence_ids} analysis={analysis} /></div>
          </div>
          {analysis.findings.limitations.length > 0 && <div><h5 className="mb-2 text-xs font-semibold">Limitations</h5><ul className="list-inside list-disc space-y-1 text-xs text-muted-foreground">{analysis.findings.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div>}
        </div>
      )}
    </section>
  );
}

export default function GroqAnalysisPanel({ result }: { result: PricePredictionResponse }) {
  const [session, setSession] = useState({ result, version: 0 });
  // Reset the entire session when the selected immutable forecast changes, even
  // if its market and timestamps match. Cleanup aborts stale browser responses.
  if (session.result !== result) setSession({ result, version: session.version + 1 });
  return <AnalysisSession key={session.version} result={result} />;
}
