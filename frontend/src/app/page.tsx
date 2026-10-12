import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, Crosshair } from "lucide-react";

import StudioNavigation from "@/components/layout/StudioNavigation";
import Controllers from "@/components/controllers/Controllers";
import Dashboard from "@/components/dashboard/Dashboard";

export default function Home() {
  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[224px_minmax(0,1fr)]">
      <StudioNavigation active="workspace" />
      <main className="min-w-0">
        <div className="flex min-h-[52px] flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-3 sm:px-9">
          <span className="terminal-kicker">KRONOS / RESEARCH WORKSPACE / 001</span>
          <div className="flex items-center gap-5">
            <span className="terminal-kicker hidden items-center gap-2 sm:inline-flex"><span className="size-1.5 bg-[#FF3D00]" /> READ-ONLY ENVIRONMENT</span>
            <Link href="/saved-results" className="terminal-link inline-flex items-center gap-1.5">Saved results <ArrowUpRight size={13} strokeWidth={1.5} /></Link>
          </div>
        </div>

        <div className="mx-auto max-w-[1800px]">
          <section className="relative overflow-hidden border-b border-border px-6 pb-9 pt-12 sm:px-9 sm:pb-12 sm:pt-14 2xl:pt-16">
            <div className="pointer-events-none absolute -right-10 top-2 hidden select-none font-sans text-[clamp(11rem,24vw,25rem)] font-black leading-none tracking-[-0.09em] text-foreground/[0.025] lg:block" aria-hidden="true">K.</div>
            <div className="relative">
              <div className="flex items-center gap-3">
                <span className="h-0.5 w-10 bg-[#FF3D00]" />
                <span className="terminal-kicker !text-[#FF3D00]">THE FORECASTING WORKSPACE</span>
              </div>
              <h1 className="terminal-heading mt-6 max-w-[1100px] text-[clamp(3.7rem,7vw,7.4rem)]">
                THE NEXT<br />
                <span className="text-[#FF3D00]">MOVE.</span><span className="text-foreground"> /</span>
              </h1>
              <div className="mt-7 flex flex-col items-start justify-between gap-6 lg:flex-row lg:items-end">
                <p className="max-w-[580px] text-[15px] leading-[1.75] text-muted-foreground sm:text-base">
                  Six forecasting engines. One deliberate workspace. Compare market history with projected paths, examine model agreement, and keep uncertainty in view.
                </p>
                <a href="#forecast-workspace" className="terminal-link group inline-flex min-h-11 items-center gap-3 border-b-2 border-[#FF3D00] text-[#FF3D00]">
                  Open the workspace
                  <ArrowDownRight size={17} strokeWidth={1.5} className="transition-transform duration-150 group-hover:translate-y-0.5" />
                </a>
              </div>
              <div className="mt-10 grid grid-cols-2 gap-0 border-t border-border sm:grid-cols-3">
                <div className="border-r border-border py-5 pr-5">
                  <div className="terminal-heading text-4xl text-foreground sm:text-5xl">06<span className="text-[#FF3D00]">.</span></div>
                  <div className="terminal-kicker mt-2">FORECAST ENGINES</div>
                </div>
                <div className="py-5 pl-5 sm:border-r sm:border-border sm:px-7">
                  <div className="terminal-heading text-4xl text-foreground sm:text-5xl">02<span className="text-[#FF3D00]">.</span></div>
                  <div className="terminal-kicker mt-2">RUN MODES</div>
                </div>
                <div className="col-span-2 flex items-end justify-between gap-3 border-t border-border py-5 sm:col-span-1 sm:border-t-0 sm:pl-7">
                  <div>
                    <div className="terminal-heading text-4xl text-foreground sm:text-5xl">00<span className="text-[#FF3D00]">.</span></div>
                    <div className="terminal-kicker mt-2">TRADE EXECUTIONS</div>
                  </div>
                  <Crosshair size={27} strokeWidth={1} className="mb-1 text-muted-foreground/60" aria-hidden="true" />
                </div>
              </div>
            </div>
          </section>

          <section id="forecast-workspace" className="px-6 pb-16 pt-11 sm:px-9 sm:pt-14">
            <div className="mb-8 flex flex-wrap items-end justify-between gap-5">
              <div>
                <span className="terminal-kicker"><span className="terminal-accent">01</span> / ACTIVE RESEARCH</span>
                <h2 className="terminal-heading mt-3 text-[clamp(2.3rem,4.6vw,4.25rem)]">YOUR WORKSPACE<span className="terminal-accent">.</span></h2>
              </div>
              <span className="terminal-kicker max-w-[280px] border-l-2 border-[#FF3D00] pl-3 leading-[1.8]">MODEL OUTPUTS ARE NOT INVESTMENT ADVICE</span>
            </div>

            <div className="grid min-w-0 grid-cols-1 border border-border xl:grid-cols-[342px_minmax(0,1fr)] 2xl:grid-cols-[370px_minmax(0,1fr)]">
              <aside className="min-w-0 border-b border-border bg-card xl:border-b-0 xl:border-r" aria-label="Prediction configuration">
                <Controllers />
              </aside>
              <div className="min-w-0 bg-background">
                <Dashboard />
              </div>
            </div>
          </section>

          <footer className="flex flex-col gap-4 border-t border-border px-6 py-7 sm:flex-row sm:items-center sm:justify-between sm:px-9">
            <span className="terminal-kicker">KRONOS / BUILT FOR EVIDENCE, NOT CERTAINTY.</span>
            <div className="flex items-center gap-5">
              <Link href="/saved-results" className="terminal-link text-muted-foreground">Archive <ArrowUpRight size={12} className="inline" /></Link>
              <span className="terminal-kicker">V2 / DESIGN PREVIEW</span>
            </div>
          </footer>
        </div>
      </main>
    </div>
  );
}
