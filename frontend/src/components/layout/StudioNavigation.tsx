import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, ChartNoAxesCombined, Layers3, Radar } from "lucide-react";

type StudioNavigationProps = {
  active: "workspace" | "archive" | "analysis";
};

const linkBase = "group flex min-h-12 items-center justify-between border-l-2 px-4 text-[12px] font-semibold tracking-[0.02em] transition-colors duration-150 focus-visible:outline-offset-[-3px]";
const activeClass = "border-[#FF3D00] bg-[#FF3D00]/[0.08] text-foreground";
const inactiveClass = "border-transparent text-muted-foreground hover:border-border hover:text-foreground";

export default function StudioNavigation({ active }: StudioNavigationProps) {
  return (
    <aside className="relative z-20 border-b border-border bg-[#0D0D0D] lg:min-h-screen lg:border-b-0 lg:border-r lg:border-border">
      <div className="flex items-center justify-between gap-5 px-6 py-5 lg:sticky lg:top-0 lg:flex-col lg:items-stretch lg:gap-0 lg:px-0 lg:py-0">
        <Link href="/" className="flex items-center gap-3 lg:border-b lg:border-border lg:px-6 lg:py-7" aria-label="Kronos Studio home">
          <span className="terminal-heading flex size-10 shrink-0 items-center justify-center border border-[#FF3D00] text-xl text-[#FF3D00]" aria-hidden="true">
            K
          </span>
          <span className="flex flex-col">
            <strong className="font-sans text-[18px] font-black leading-none tracking-[-0.065em]">KRONOS<span className="text-[#FF3D00]">.</span></strong>
            <span className="terminal-kicker mt-1 !text-[9px] !tracking-[0.08em]">FORECAST TERMINAL</span>
          </span>
        </Link>

        <nav aria-label="Primary" className="hidden flex-col lg:flex lg:pt-9">
          <div className="terminal-kicker mb-4 px-6">/ NAVIGATION</div>
          <Link href="/" aria-current={active === "workspace" ? "page" : undefined} className={linkBase + " " + (active === "workspace" ? activeClass : inactiveClass)}>
            <span className="flex items-center gap-3"><ChartNoAxesCombined size={16} strokeWidth={1.5} /> Workspace</span>
            <span className="terminal-mono text-[10px] text-muted-foreground">01</span>
          </Link>
          <Link href="/saved-results" aria-current={active === "archive" ? "page" : undefined} className={linkBase + " " + (active === "archive" ? activeClass : inactiveClass)}>
            <span className="flex items-center gap-3"><Layers3 size={16} strokeWidth={1.5} /> Saved research</span>
            <ArrowUpRight size={14} strokeWidth={1.5} className="text-muted-foreground" />
          </Link>
          <Link href="/ai-analysis" aria-current={active === "analysis" ? "page" : undefined} className={linkBase + " " + (active === "analysis" ? activeClass : inactiveClass)}>
            <span className="flex items-center gap-3"><Radar size={16} strokeWidth={1.5} /> AI analysis</span>
            <ArrowDownRight size={14} strokeWidth={1.5} />
          </Link>
          <p className="terminal-mono px-6 pt-2 text-[10px] leading-relaxed text-muted-foreground">Independent market analysis. Runs on click.</p>
        </nav>

        <div className="flex items-center gap-2 lg:hidden">
          <Link href="/" className={"terminal-link px-2 py-2 " + (active === "workspace" ? "text-[#FF3D00]" : "text-muted-foreground")}>Studio</Link>
          <Link href="/saved-results" className={"terminal-link px-2 py-2 " + (active === "archive" ? "text-[#FF3D00]" : "text-muted-foreground")}>Archive</Link>
          <Link href="/ai-analysis" className={"terminal-link px-2 py-2 " + (active === "analysis" ? "text-[#FF3D00]" : "text-muted-foreground")}>AI</Link>
        </div>

        <div className="hidden lg:mt-[min(18vh,220px)] lg:block lg:border-t lg:border-border lg:px-6 lg:py-8">
          <span className="terminal-kicker">/ SYSTEM STATUS</span>
          <div className="mt-5 flex items-center gap-2">
            <span className="size-1.5 bg-[#FF3D00]" aria-hidden="true" />
            <span className="terminal-mono text-[11px] text-foreground">RESEARCH ONLY</span>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">Forecasts are estimates. AI analysis runs manually. Trade execution is disabled.</p>
          <div className="mt-8 flex items-center gap-2 border-t border-border pt-5 text-muted-foreground">
            <ArrowDownRight size={16} strokeWidth={1.5} />
            <span className="terminal-kicker !text-[9px]">EXPERIMENTAL / V2.0</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
