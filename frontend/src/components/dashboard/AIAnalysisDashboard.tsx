"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { analyzeMarket, getAIProviders } from "@/lib/api/groqAnalysis";
import type { AIProviders, GroqAnalysisResponse, TradingAgentsResponse, MarketAnalysisInput } from "@/schemas/groqAnalysisSchema";
import AnalysisResults from "./AnalysisResults";

const selectClass = "h-10 w-full min-w-0 border border-border bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-[#FF3D00]";
const statusLabels = {ready:"Ready",not_configured:"Not connected",quota_exhausted:"Quota exhausted",cooldown:"Temporarily unavailable",tracker_unavailable:"Usage tracking unavailable"};
const defaultInput: MarketAnalysisInput = {symbol:"ETHUSDT",interval:"5m",lookback:200,data_source:"binance",period:"1mo",mode:"single"};

export default function AIAnalysisDashboard() {
  const [input,setInput] = useState(defaultInput);
  const [analysis,setAnalysis] = useState<GroqAnalysisResponse | TradingAgentsResponse | null>(null);
  const [providers,setProviders] = useState<AIProviders | null>(null);
  const [error,setError] = useState<string | null>(null);
  const [loading,setLoading] = useState(false);
  const active = useRef<AbortController | null>(null);
  const statusRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    statusRequest.current = controller;
    getAIProviders(controller.signal).then(setProviders).catch(() => { if(!controller.signal.aborted) setError("Provider status could not be loaded."); });
    return () => { controller.abort(); active.current?.abort(); statusRequest.current?.abort(); };
  },[]);

  function change(patch:Partial<MarketAnalysisInput>) {
    active.current?.abort(); active.current=null;
    setLoading(false);setAnalysis(null);setError(null);setInput(value=>({...value,...patch}));
  }
  async function refreshProviders() {
    statusRequest.current?.abort();
    const controller=new AbortController();statusRequest.current=controller;
    try { const next=await getAIProviders(controller.signal);if(!controller.signal.aborted)setProviders(next); }
    catch { if(!controller.signal.aborted)setError("Provider status could not be refreshed."); }
  }
  async function run(event:React.FormEvent) {
    event.preventDefault();if(active.current)return;
    const controller=new AbortController();active.current=controller;
    setLoading(true);setError(null);setAnalysis(null);
    try { const result=await analyzeMarket(input,controller.signal);if(!controller.signal.aborted)setAnalysis(result); }
    catch(cause) { if(!controller.signal.aborted)setError(cause instanceof TypeError ? "Cannot reach the local analysis service." : cause instanceof Error ? cause.message : "Analysis failed."); }
    finally { if(!controller.signal.aborted){setLoading(false);active.current=null;await refreshProviders();} }
  }
  return <div className="space-y-6">
    <form onSubmit={run} className="border border-border bg-card p-5 sm:p-7" aria-label="Market analysis settings">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="space-y-2 text-xs text-muted-foreground">Market source<select aria-label="Market source" className={selectClass} value={input.data_source} onChange={e=>change({data_source:e.target.value as MarketAnalysisInput["data_source"],symbol:e.target.value==="yfinance"?"AAPL":"ETHUSDT",interval:e.target.value==="yfinance"?"1d":"5m",period:e.target.value==="yfinance"?"1y":"1mo"})}><option value="binance">Binance</option><option value="yfinance">Yahoo Finance</option></select></label>
        <label className="space-y-2 text-xs text-muted-foreground">Symbol<Input aria-label="Market symbol" required maxLength={32} value={input.symbol} onChange={e=>change({symbol:e.target.value})} /></label>
        <label className="space-y-2 text-xs text-muted-foreground">Interval<select aria-label="Candle interval" className={selectClass} value={input.interval} onChange={e=>change({interval:e.target.value as MarketAnalysisInput["interval"]})}>{["1m","5m","15m","30m","1h",...(input.data_source==="binance"?["4h"]:[]),"1d","1w"].map(value=><option key={value} value={value}>{value}</option>)}</select></label>
        <label className="space-y-2 text-xs text-muted-foreground">Completed candles<Input aria-label="Completed candles" type="number" min={35} max={999} required value={input.lookback} onChange={e=>change({lookback:Number(e.target.value)})} /></label>
        {input.data_source==="yfinance"&&<label className="space-y-2 text-xs text-muted-foreground">History period<select aria-label="History period" className={selectClass} value={input.period} onChange={e=>change({period:e.target.value as MarketAnalysisInput["period"]})}>{["1mo","3mo","1y","2y","5y","max"].map(value=><option key={value} value={value}>{value}</option>)}</select></label>}
        <label className="space-y-2 text-xs text-muted-foreground">Analysis mode<select aria-label="Analysis mode" className={selectClass} value={input.mode} onChange={e=>change({mode:e.target.value as MarketAnalysisInput["mode"]})}><option value="single">Market assessment</option><option value="agents">TradingAgents review</option></select></label>
      </div>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border-t border-border pt-5">
        <p className="max-w-xl text-xs leading-relaxed text-muted-foreground">Analyze completed market candles directly. GPT-OSS-120B only, with automatic provider fallback. {input.mode==="agents"?"Three research turns.":"One assessment."}</p>
        <Button type="submit" disabled={loading}>{loading?"Analyzing…":"Analyze market"}</Button>
      </div>
    </form>
    <section aria-labelledby="providers-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="providers-heading" className="text-sm font-semibold">Provider connections</h2><Button type="button" variant="ghost" size="sm" onClick={refreshProviders}>Refresh status</Button></div>
      <p className="text-xs text-muted-foreground">Automatic order: Groq → Routeway → OpenRouter. Quota failures switch immediately.</p>
      {providers ? <div className="grid gap-3 sm:grid-cols-3">{providers.providers.map(provider=><article key={provider.provider} className="min-w-0 border border-border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold capitalize">{provider.provider}</h3><span className="text-[11px] text-muted-foreground">{statusLabels[provider.status]}</span></div>
        <p className="terminal-mono mt-3 break-words text-[10px] text-muted-foreground">GPT-OSS-120B</p>
        {provider.quota && <p className="terminal-mono mt-2 text-[11px] text-muted-foreground">{provider.quota.tokens_observed.toLocaleString()} recorded tokens · {provider.quota.requests_used} requests</p>}
        <p className="mt-2 text-xs text-muted-foreground">{provider.quota?.usage_percent != null ? `${provider.quota.usage_percent.toFixed(2)}% recorded usage · ${provider.quota.cap_percent}% ceiling` : "Account allowance not reported."}</p>
      </article>)}</div> : <p className="text-xs text-muted-foreground">Loading provider status…</p>}
    </section>
    {loading && <p role="status" className="text-sm text-muted-foreground">Loading completed candles and reviewing the Python evidence…</p>}
    {error && <p role="alert" className="border border-destructive/40 p-4 text-sm text-destructive">{error}</p>}
    {analysis && <AnalysisResults analysis={analysis} />}
  </div>;
}
