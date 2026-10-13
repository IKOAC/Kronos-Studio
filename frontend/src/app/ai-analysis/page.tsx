import Link from "next/link";
import StudioNavigation from "@/components/layout/StudioNavigation";
import AIAnalysisDashboard from "@/components/dashboard/AIAnalysisDashboard";

export default function AIAnalysisPage() {
  return <div className="min-h-screen bg-background lg:grid lg:grid-cols-[224px_minmax(0,1fr)]">
    <StudioNavigation active="analysis" />
    <main className="min-w-0">
      <div className="border-b border-border px-6 py-4 sm:px-9"><span className="terminal-kicker">KRONOS / AI ANALYSIS</span></div>
      <div className="mx-auto max-w-[1600px] space-y-6 px-6 py-7 sm:px-9">
        <div><h1 className="text-2xl font-bold tracking-tight">AI analysis</h1><p className="mt-2 text-sm text-muted-foreground">Market evidence, technical indicators, and research assessments.</p></div>
        <Link href="/signal-scanner" className="inline-flex items-center gap-2 border border-[#ff8a62]/40 px-4 py-3 text-sm text-[#ff8a62]">Signal scanner — explore pairs with a live agent discussion →</Link>
        <AIAnalysisDashboard />
      </div>
    </main>
  </div>;
}
