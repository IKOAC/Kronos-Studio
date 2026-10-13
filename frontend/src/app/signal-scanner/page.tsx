import Link from "next/link";
import StudioNavigation from "@/components/layout/StudioNavigation";
import SignalScanner from "@/components/dashboard/SignalScanner";

export default function SignalScannerPage() {
  return <div className="min-h-screen bg-background lg:grid lg:grid-cols-[224px_minmax(0,1fr)]">
    <StudioNavigation active="scanner"/>
    <main className="min-w-0">
      <div className="border-b border-border px-6 py-4 sm:px-9"><span className="terminal-kicker">KRONOS / SIGNAL SCANNER</span></div>
      <div className="mx-auto max-w-[1600px] space-y-6 px-6 py-7 sm:px-9">
        <div className="flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-2xl font-bold tracking-tight">Signal scanner</h1><p className="mt-2 text-sm text-muted-foreground">Find a clear setup. Watch the researchers challenge it.</p></div><Link href="/ai-analysis" className="text-xs text-muted-foreground underline underline-offset-4">Single-market analysis</Link></div>
        <SignalScanner/>
      </div>
    </main>
  </div>;
}
