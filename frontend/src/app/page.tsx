import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

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
          <section id="forecast-workspace" className="px-6 pb-16 pt-8 sm:px-9 sm:pt-10">
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
