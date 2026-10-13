import type { GroqAnalysisResponse, TradingAgentsResponse } from "@/schemas/groqAnalysisSchema";

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


export default function AnalysisResults({ analysis }: { analysis: GroqAnalysisResponse | TradingAgentsResponse }) {
  const technical = analysis.metrics.technical;
  const forecast = analysis.metrics.forecast;
  const metrics = [
    ["Last close", format(technical.last_close)], ["RSI (14)", format(technical.rsi_14)],
    ["MACD (12/26)", format(technical.macd_12_26)], ["MACD signal (9)", format(technical.macd_signal_9)],
    ["EMA (20)", format(technical.ema_20)], ["EMA (50)", format(technical.ema_50)],
    ["ATR (14)", format(technical.atr_14)], ["Volume ratio (20)", format(technical.volume_ratio_20)],
    ["Bollinger lower (20)", format(technical.bollinger_lower_20)], ["Bollinger upper (20)", format(technical.bollinger_upper_20)],
  ];
  if (forecast) metrics.push(["Model agreement", format(forecast.agreement_pct, "%")], ["Forecast dispersion", format(forecast.dispersion_std_pct, " pp")]);
  return (
    <section id="analysis-results" className="min-w-0 space-y-5 border border-border bg-card p-5 sm:p-7" aria-labelledby="assessment-heading">
      <div>
        <p className="terminal-kicker">{analysis.symbol} / {analysis.interval}</p>
        <h2 id="assessment-heading" className="mt-2 text-lg font-bold">{"agents" in analysis ? "TradingAgents assessment" : "Market assessment"}</h2>
        <p className="terminal-mono mt-2 text-[11px] text-muted-foreground">GPT-OSS-120B · {analysis.providers_used.length ? analysis.providers_used.join(" → ") : analysis.provider}</p>
        <p className="mt-4 text-sm leading-relaxed" aria-live="polite">{analysis.findings.summary}</p>
        {analysis.market_data && <p className="mt-3 break-words text-xs text-muted-foreground">{analysis.market_data.candles} completed candles · {analysis.market_data.data_source} · last candle opened {analysis.market_data.last_timestamp} · fetched {analysis.market_data.retrieved_at_utc}</p>}
      </div>
      {"agents" in analysis && <div className="space-y-3">
        <p className="terminal-mono text-[11px] text-muted-foreground">{analysis.run_stats.requests_used} provider requests · {analysis.run_stats.tokens_used.toLocaleString()} recorded tokens · {(analysis.run_stats.elapsed_ms / 1000).toFixed(2)}s</p>
        {analysis.agents.filter(a => a.role !== "research_manager").map(agent => <details key={agent.role} className="border border-border p-3">
          <summary className="cursor-pointer text-xs font-semibold">{agent.role === "bull" ? "Bull researcher" : "Bear researcher"}</summary>
          <p className="mt-3 text-sm leading-relaxed">{agent.findings.summary}</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <div><h3 className="mb-2 text-xs font-semibold">Supporting evidence</h3><Evidence ids={agent.findings.supporting_evidence_ids} analysis={analysis} /></div>
            <div><h3 className="mb-2 text-xs font-semibold">Conflicting evidence</h3><Evidence ids={agent.findings.conflicting_evidence_ids} analysis={analysis} /></div>
          </div>
        </details>)}
      </div>}
      <dl className="grid grid-cols-2 gap-4 border-y border-border py-5 sm:grid-cols-3 lg:grid-cols-4">
        {metrics.map(([label,value]) => <div key={label} className="min-w-0"><dt className="text-[11px] text-muted-foreground">{label}</dt><dd className="terminal-mono mt-1 break-words text-sm">{value}</dd></div>)}
      </dl>
      <p className="text-xs text-muted-foreground">Metrics calculated by Python. — indicates insufficient history for the indicator.</p>
      <div className="grid gap-5 sm:grid-cols-2">
        <div><h3 className="mb-2 text-xs font-semibold">Supporting evidence</h3><Evidence ids={analysis.findings.supporting_evidence_ids} analysis={analysis} /></div>
        <div><h3 className="mb-2 text-xs font-semibold">Conflicting evidence</h3><Evidence ids={analysis.findings.conflicting_evidence_ids} analysis={analysis} /></div>
      </div>
      {analysis.findings.limitations.length > 0 && <div><h3 className="mb-2 text-xs font-semibold">Limitations</h3><ul className="list-inside list-disc space-y-1 text-xs text-muted-foreground">{analysis.findings.limitations.map(item => <li key={item}>{item}</li>)}</ul></div>}
      {analysis.provider_attempts.some(a => a.status !== "succeeded") && <p className="text-xs text-muted-foreground">Recovered after {analysis.provider_attempts.filter(a => a.status !== "succeeded").map(a => `${a.provider} (${a.status})`).join(", ")}.</p>}
    </section>
  );
}
