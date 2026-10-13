"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, Circle, Radio, ScanLine, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { runSignalScan, scannerErrors } from "@/lib/api/signalScanner";
import type { ScannerEvent, ScannerMessage, ScannerRole, ScannerSetup } from "@/schemas/signalScannerSchema";

const roles: {id:ScannerRole;name:string;label:string;color:string}[] = [
  {id:"bull",name:"Bull researcher",label:"Builds the case",color:"#73d9ac"},
  {id:"bear",name:"Bear researcher",label:"Challenges the case",color:"#ed9a82"},
  {id:"research_manager",name:"Research manager",label:"Weighs both sides",color:"#adabff"},
];
const price=(v:number)=>v.toLocaleString(undefined,{maximumFractionDigits:v<1?6:v<100?4:2});
const pair=(symbol:string)=>symbol.replace(/USDT$/," / USDT");
const selectClass="h-10 w-full border border-border bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-[#FF3D00]";

function SetupChart({setup}:{setup:ScannerSetup}) {
  const values=[...setup.chart.map(p=>p.close),setup.entry,setup.stop,setup.target];
  const min=Math.min(...values),max=Math.max(...values),padding=(max-min)*0.15||1;
  const y=(value:number)=>145-(value-min+padding)/(max-min+2*padding)*130;
  const path=setup.chart.map((p,i)=>`${i===0?"M":"L"} ${12+i/Math.max(1,setup.chart.length-1)*420} ${y(p.close)}`).join(" ");
  return <svg viewBox="0 0 580 164" role="img" aria-label={`${setup.symbol} recent closes with conditional entry, stop, and target`} className="mt-5 w-full overflow-visible">
    <path d={path} fill="none" stroke="#858a92" strokeWidth="2" />
    {[{name:"TARGET",value:setup.target,color:"#73d9ac"},{name:"ENTRY",value:setup.entry,color:"#ff8a62"},{name:"STOP",value:setup.stop,color:"#ed9a82"}].map(level=><g key={level.name}>
      <line x1="12" x2="450" y1={y(level.value)} y2={y(level.value)} stroke={level.color} strokeDasharray="4 4" opacity=".6"/>
      <text x="458" y={y(level.value)+4} fill={level.color} fontSize="10" fontFamily="monospace">{level.name} {price(level.value)}</text>
    </g>)}
  </svg>;
}

export default function SignalScanner() {
  const [interval,setIntervalValue]=useState<"15m"|"1h">("15m");
  const [pairs,setPairs]=useState(2);
  const [running,setRunning]=useState(false);
  const [phase,setPhase]=useState("Ready to scan");
  const [setups,setSetups]=useState<ScannerSetup[]>([]);
  const [shortlist,setShortlist]=useState<string[]>([]);
  const [current,setCurrent]=useState<string|null>(null);
  const [viewedPair,setViewedPair]=useState<string|null>(null);
  const [activeRole,setActiveRole]=useState<ScannerRole|null>(null);
  const [messages,setMessages]=useState<ScannerMessage[]>([]);
  const [outcomes,setOutcomes]=useState<Record<string,{qualified:boolean;reason:string}>>({});
  const [signal,setSignal]=useState<{setup:ScannerSetup;summary:string}|null>(null);
  const [error,setError]=useState<string|null>(null);
  const [finished,setFinished]=useState(false);
  const [clock,setClock]=useState(0);
  const controller=useRef<AbortController|null>(null);
  const feed=useRef<HTMLDivElement|null>(null);
  useEffect(()=>()=>controller.current?.abort(),[]);
  useEffect(()=>{const id=window.setInterval(()=>setClock(Date.now()),1000);return()=>window.clearInterval(id);},[]);
  useEffect(()=>{feed.current?.scrollTo({top:feed.current.scrollHeight,behavior:"smooth"});},[messages.length]);
  const expired=signal ? clock>=Date.parse(signal.setup.expires_at):false;
  const discussionPair=viewedPair??current;
  const currentMessages=messages.filter(m=>m.data.symbol===discussionPair);
  const reviewedPairs=[...new Set(messages.map(m=>m.data.symbol))];

  function receive(event:ScannerEvent) {
    switch(event.type) {
      case "scan_started":setPhase("Checking liquidity and spreads");break;
      case "screening":setPhase(`Screening ${pair(event.data.symbol)}`);break;
      case "screened":setSetups(previous=>[...previous.filter(s=>s.symbol!==event.data.setup.symbol),event.data.setup]);break;
      case "shortlist":setShortlist(event.data.symbols);break;
      case "pair_started":setCurrent(event.data.setup.symbol);setViewedPair(event.data.setup.symbol);setActiveRole(null);setPhase(`Opening the debate · ${pair(event.data.setup.symbol)}`);break;
      case "agent_started":setActiveRole(event.data.role);setPhase(`${roles.find(r=>r.id===event.data.role)?.name} is reviewing ${pair(event.data.symbol)}`);break;
      case "agent_completed":setMessages(previous=>[...previous,event]);setActiveRole(null);break;
      case "pair_completed":setOutcomes(previous=>({...previous,[event.data.setup.symbol]:{qualified:event.data.qualified,reason:event.data.reason}}));break;
      case "signal":setSignal(event.data);break;
      case "scan_completed":setPhase(event.data.message);setFinished(true);setActiveRole(null);break;
      case "scan_error":setError(scannerErrors[event.data.code]??event.data.message);setPhase("Scan paused");setActiveRole(null);break;
    }
  }
  async function start() {
    if(controller.current)return;
    const next=new AbortController();controller.current=next;
    setRunning(true);setFinished(false);setSignal(null);setError(null);setSetups([]);setShortlist([]);setCurrent(null);setViewedPair(null);setMessages([]);setOutcomes({});setActiveRole(null);setPhase("Connecting to the scanner…");
    try { await runSignalScan({interval,pairs},next.signal,event=>{if(!next.signal.aborted)receive(event);}); }
    catch(cause) { if(!next.signal.aborted){setError(cause instanceof Error?cause.message:"The scan failed.");setPhase("Scan interrupted");} }
    finally { if(controller.current===next){controller.current=null;setRunning(false);setActiveRole(null);} }
  }
  function stop() {
    controller.current?.abort();setPhase("Stopped. The current provider request may finish before another scan can start.");setActiveRole(null);
  }

  return <div className="space-y-6">
    <section className="border border-border bg-card p-5 sm:p-7" aria-label="Scanner settings">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="max-w-xl"><div className="terminal-kicker flex items-center gap-2 text-[#ff8a62]"><ScanLine size={14}/> LIQUID PAIRS / LIVE RESEARCH</div><h2 className="mt-3 text-lg font-semibold">Let the evidence earn the signal.</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">A shuffled sample of major crypto pairs. Six technical checks. Three researchers challenging the same setup. The scan stops at the first qualifying entry.</p></div>
        <div className="grid w-full gap-3 sm:w-auto sm:grid-cols-[110px_100px_auto] sm:items-end">
          <label className="space-y-2 text-xs text-muted-foreground">Timeframe<select aria-label="Scanner timeframe" value={interval} disabled={running} onChange={e=>setIntervalValue(e.target.value as "15m"|"1h")} className={selectClass}><option value="15m">15 minutes</option><option value="1h">1 hour</option></select></label>
          <label className="space-y-2 text-xs text-muted-foreground">Review up to<select aria-label="Pairs to review" value={pairs} disabled={running} onChange={e=>setPairs(Number(e.target.value))} className={selectClass}>{[1,2,3].map(n=><option key={n} value={n}>{n} {n===1?"pair":"pairs"}</option>)}</select></label>
          {running?<Button type="button" variant="outline" onClick={stop}><Square size={12}/> Stop scan</Button>:<Button type="button" onClick={start}><Radio size={15}/> {finished||error?"Scan again":"Start scan"}</Button>}
        </div>
      </div>
      <div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 border-t border-border pt-4 text-[11px] text-muted-foreground"><span>BTC · ETH · SOL · BNB · XRP · ADA · LINK · AVAX</span><span>24h volume ≥ $50M</span><span>Spread ≤ 0.08%</span><span>Groq · GPT-OSS-120B</span></div>
    </section>

    <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_330px]">
      <section className="min-w-0 border border-border bg-card" aria-labelledby="debate-title">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4"><h2 id="debate-title" className="terminal-kicker">/ THE RESEARCH ROOM</h2><span className="terminal-mono text-xs text-[#ff8a62]">{discussionPair?pair(discussionPair):"Awaiting a candidate"}</span></div>
        <div className="grid grid-cols-3 gap-2 px-4 py-7 sm:gap-4 sm:px-6">
          {roles.map((role,index)=>{
            const completed=currentMessages.some(m=>m.data.role===role.id);const active=discussionPair===current&&activeRole===role.id;
            return <div key={role.id} className="relative text-center">
              {index<2&&<div aria-hidden="true" className="absolute left-[65%] top-6 flex w-[74%] items-center text-muted-foreground/40"><div className={`h-px flex-1 ${completed?"bg-[#ff8a62]/60":"bg-border"}`}/><ArrowRight size={12}/></div>}
              <div style={{color:role.color,borderColor:active?role.color:undefined}} className={`relative z-10 mx-auto flex size-12 items-center justify-center rounded-full border bg-card font-mono text-sm ${active?"motion-safe:animate-pulse shadow-[0_0_24px_#ff3d0015]":"border-border"}`}>{completed?<Check size={18}/>:index===0?"B+":index===1?"B−":"RM"}</div>
              <h3 className="mt-3 text-[11px] font-semibold sm:text-xs">{role.name}</h3><p className="mt-1 text-[10px] text-muted-foreground">{active?"Reviewing…":completed?"Review delivered":role.label}</p>
            </div>;
          })}
        </div>
        <div role="status" className="flex items-center gap-2 border-y border-border bg-background/40 px-5 py-3 text-xs text-muted-foreground"><span className={`size-1.5 shrink-0 rounded-full ${running?"bg-[#ff8a62] motion-safe:animate-pulse":"bg-muted-foreground"}`}/>{phase}</div>
        {reviewedPairs.length>1&&<nav aria-label="Reviewed pair discussions" className="flex flex-wrap gap-2 border-b border-border px-5 py-3">{reviewedPairs.map(symbol=><button key={symbol} type="button" onClick={()=>setViewedPair(symbol)} aria-pressed={discussionPair===symbol} className={`border px-3 py-1.5 text-xs ${discussionPair===symbol?"border-[#ff8a62] text-[#ff8a62]":"border-border text-muted-foreground"}`}>{pair(symbol)} · {messages.filter(m=>m.data.symbol===symbol).length}/3</button>)}</nav>}
        <div ref={feed} role="log" aria-label="Agent discussion" aria-live="polite" className="max-h-[540px] min-h-[260px] space-y-5 overflow-y-auto p-5 sm:p-6">
          {messages.length===0?<div className="flex min-h-[210px] flex-col items-center justify-center text-center"><Radio size={30} strokeWidth={1} className="text-muted-foreground/40"/><p className="mt-4 text-sm text-muted-foreground">The discussion will appear here as each review arrives.</p><p className="mt-2 max-w-sm text-xs leading-5 text-muted-foreground/60">Bull makes the case. Bear challenges it. The manager reads both and gives a verdict. Reviews can take a few minutes while Groq refills its allowance.</p></div>:messages.map((message,index)=>{
            const role=roles.find(r=>r.id===message.data.role)!;const verdict=message.data.findings.setup_verdict;
            return <article key={`${message.data.symbol}-${message.data.role}-${index}`} className="flex gap-3">
              <div style={{color:role.color}} className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-full border border-border font-mono text-[10px]">{message.data.role==="bull"?"B+":message.data.role==="bear"?"B−":"RM"}</div>
              <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2 text-xs"><strong style={{color:role.color}}>{role.name}</strong><span className="text-muted-foreground">{pair(message.data.symbol)}</span><span className={`ml-auto text-[10px] ${verdict==="supports"?"text-emerald-300":verdict==="rejects"?"text-orange-300":"text-muted-foreground"}`}>{verdict==="supports"?"SUPPORTS SETUP":verdict==="rejects"?"CHALLENGES SETUP":"INCONCLUSIVE"}</span></div>
                <p className="mt-2 text-sm leading-6">{message.data.findings.summary}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">{message.data.findings.supporting_evidence_ids.map(id=><span key={id} className="border border-border px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">{id.replace("technical.","").replace("scanner.","setup.")}</span>)}</div>
                {message.data.findings.limitations.length>0&&<p className="mt-2 text-[11px] leading-5 text-muted-foreground">{message.data.findings.limitations.join(" ")}</p>}
              </div>
            </article>;
          })}
        </div>
      </section>

      <aside className="space-y-4">
        <section className="border border-border bg-card p-5"><h2 className="terminal-kicker">/ CANDIDATE BOARD</h2><p className="mt-2 text-xs leading-5 text-muted-foreground">Shuffled liquid pairs, ranked by checks passed. Reviewed candidates are marked below.</p>
          <div className="mt-5 space-y-3">{setups.length===0?<p className="py-6 text-center text-xs text-muted-foreground/60">Start a scan to screen the market.</p>:setups.map(setup=><div key={setup.symbol} className={`border p-3 ${current===setup.symbol?"border-[#ff8a62]/50":"border-border"}`}>
            <div className="flex items-center justify-between text-xs"><strong>{pair(setup.symbol)}</strong><span className="terminal-mono text-muted-foreground">{setup.checks_passed}/{setup.checks.length}</span></div>
            <div className="mt-2 flex gap-1" aria-label={`${setup.checks_passed} of ${setup.checks.length} checks passed`}>{setup.checks.map(check=><div title={`${check.label}: ${check.detail}`} key={check.label} className={`h-1 flex-1 ${check.passed?"bg-emerald-400/70":"bg-border"}`}/>)}</div>
            <p className="mt-2 text-[10px] leading-4 text-muted-foreground">{outcomes[setup.symbol]?.reason??(shortlist.includes(setup.symbol)?"Selected for agent review":`${setup.side.toUpperCase()} hypothesis · screened`)}</p>
          </div>)}</div>
        </section>
        <div className="border border-border/70 p-4 text-[11px] leading-5 text-muted-foreground">A qualifying setup requires every technical check and three supporting verdicts. These rules have no measured win rate. Entries are conditional research levels; orders are never placed.</div>
      </aside>
    </div>

    {error&&<div role="alert" className="border border-orange-400/40 bg-orange-400/5 p-5 text-sm text-orange-200">{error}</div>}
    {signal&&<section className={`border bg-card p-5 sm:p-7 ${expired?"border-border":"border-emerald-400/40"}`} aria-labelledby="signal-title">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><div className="terminal-kicker text-emerald-300">{expired?"/ SETUP EXPIRED":"/ QUALIFYING SETUP FOUND"}</div><h2 id="signal-title" className="mt-3 text-2xl font-semibold">{pair(signal.setup.symbol)} <span className="ml-2 text-sm font-normal uppercase text-muted-foreground">{signal.setup.side} · {signal.setup.interval}</span></h2><p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">{signal.summary}</p></div><span className="flex items-center gap-2 border border-border px-3 py-2 text-xs"><Check size={14} className="text-emerald-300"/> All checks · 3/3 reviewers</span></div>
      <div className="mt-6 grid gap-4 sm:grid-cols-4">{[{label:"Conditional entry",value:price(signal.setup.entry)},{label:"Invalidation / stop",value:price(signal.setup.stop)},{label:"Target",value:price(signal.setup.target)},{label:"Net reward / risk",value:`${signal.setup.net_reward_risk.toFixed(1)} : 1`}].map(item=><div className="border-l border-border pl-4" key={item.label}><p className="text-xs text-muted-foreground">{item.label}</p><p className="terminal-mono mt-2 text-xl">{item.value}</p></div>)}</div>
      <SetupChart setup={signal.setup}/>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{signal.setup.checks.map(check=><div key={check.label} className="flex gap-2 text-xs"><Check size={13} className="mt-0.5 shrink-0 text-emerald-300"/><div><strong>{check.label}</strong><p className="mt-1 leading-5 text-muted-foreground">{check.detail}</p></div></div>)}</div>
      <p className="mt-5 border-t border-border pt-4 text-xs leading-6 text-muted-foreground">{expired?"This snapshot has expired. Run a new scan before considering an entry.":`Watch for a breakout ${signal.setup.side==="long"?"above":"below"} the entry trigger. The setup expires at ${new Date(signal.setup.expires_at).toLocaleTimeString()}.`} Assumes {signal.setup.fee_bps} bps fees and {signal.setup.slippage_bps} bps slippage per side. Short setups describe a downside hypothesis; instrument availability is not checked.</p>
    </section>}
    {finished&&!signal&&<section className="flex gap-4 border border-border p-6"><Circle size={22} className="shrink-0 text-muted-foreground"/><div><h2 className="font-semibold">No qualifying setup this time</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">The sampled pairs did not clear all checks and the full agent review. Read the discussion above or run a new shuffled scan.</p></div></section>}
  </div>;
}
