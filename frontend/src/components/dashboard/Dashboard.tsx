"use client";
import { useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Combobox, ComboboxInput, ComboboxContent, ComboboxList, ComboboxItem } from "@/components/ui/combobox";

import InfoPanel from "./InfoPanel";
import PredictionChart from "./PredictionChart";
import ModelComparisonPanel from "./ModelComparisonPanel";
import DownloadActions from "./DownloadActions";
import SaveResultAction from "./SaveResultAction";
import { usePricePredictionStore } from "@/stores/pricePredictionStore";
import { ChartCandlestickIcon, Alert02Icon, CancelCircleIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import WaveLoader from "../WaveLoader";

const Dashboard = () => {
  const mode = usePricePredictionStore((state) => state.mode);
  const result = usePricePredictionStore((state) => state.result);
  const batchResults = usePricePredictionStore((state) => state.batchResults);
  const activeResultIndex = usePricePredictionStore((state) => state.activeResultIndex);
  const setActiveResultIndex = usePricePredictionStore((state) => state.setActiveResultIndex);
  const isLoading = usePricePredictionStore((state) => state.isLoading);
  const error = usePricePredictionStore((state) => state.error);
  const clearError = usePricePredictionStore((state) => state.clearError);

  const chartRef = useRef<HTMLDivElement>(null);

  const hasBatchResults = batchResults && batchResults.length > 0;
  const activeBatchResult = hasBatchResults ? batchResults[activeResultIndex] : null;

  // Determine which result to display
  const displayResult = mode === "batch" ? activeBatchResult : result;
  const hasResult = displayResult !== null;
  const isBatch = mode === "batch";

  // Build combobox options from batch results
  const batchOptions = hasBatchResults
    ? batchResults.map((res, index) => {
        const symbol = res.request.symbol || `Item`;
        const label = `#${index + 1} — ${symbol}`;
        const detail = `${res.request.interval} · ${res.request.data_source}`;
        const dataSource = res.request.data_source || "";
        return { value: String(index), label, detail, dataSource };
      })
    : [];

  const activeOption = batchOptions[activeResultIndex];

  /**
   * Per-index chart capturer for batch ZIP.
   * Switches the visible chart to `index`, waits two animation frames so
   * React re-renders and Recharts finishes painting, then returns the live
   * chartRef DOM node. downloadBatchAsZip calls this for every index in
   * sequence, captures SVG/PNG while the element is live, then moves on.
   */
  const captureChart = useCallback(
    async (index: number): Promise<HTMLElement | null> => {
      setActiveResultIndex(index);
      // Two rAF calls: first lets React flush the state update,
      // second lets Recharts commit its SVG paint.
      await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
      return chartRef.current;
    },
    [setActiveResultIndex]
  );

  return (
    <section className="flex h-full min-w-0 flex-col">
      <div className="border-b border-border px-5 pb-6 pt-7 sm:px-7">
        <div className="flex items-center justify-between gap-3">
          <span className="terminal-kicker"><span className="terminal-accent">02</span> / ANALYZE</span>
          <span className="terminal-mono text-[11px] text-[#FF3D00]">[ OUTPUT ]</span>
        </div>
        <h3 className="terminal-heading mt-5 text-3xl sm:text-4xl">THE MODEL<br />VIEW<span className="terminal-accent">.</span></h3>
        <p className="mt-4 max-w-xl text-sm leading-relaxed text-muted-foreground">
          Historical candles against the projected path. Compare the evidence, not just the direction.
        </p>
      </div>

      <InfoPanel />

      <div className="flex min-w-0 flex-1 flex-col gap-5 px-5 py-6 sm:px-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 bg-[#FF3D00]" aria-hidden="true" />
              <span className="terminal-kicker">PRICE ACTION / PROJECTION</span>
            </div>
            <h4 className="mt-2 text-xl font-bold tracking-[-0.04em] sm:text-2xl">Forecast canvas</h4>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              History transitions into a distinct forecast region.
            </p>
          </div>
          {hasResult && displayResult && (
            <div className="flex flex-wrap items-center gap-2">
              <SaveResultAction result={displayResult} batchResults={batchResults} isBatch={isBatch} />
              <DownloadActions chartRef={chartRef} displayResult={displayResult} batchResults={batchResults} isBatch={isBatch} captureChart={captureChart} />
            </div>
          )}
        </div>

        {mode === "batch" && hasBatchResults && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-y border-border py-4">
            <span className="terminal-kicker">BATCH RUN / SELECT RESULT</span>
            <Combobox value={activeOption ? activeOption.label : ""} onValueChange={(value) => {
              const match = batchOptions.find((opt) => opt.label === value);
              if (match) setActiveResultIndex(Number(match.value));
            }}>
              <ComboboxInput placeholder="Choose batch result…" className="w-full sm:w-64" />
              <ComboboxContent>
                <ComboboxList>
                  {batchOptions.map((opt) => (
                    <ComboboxItem key={opt.value} value={opt.label} className="cursor-pointer">
                      <div className="flex flex-col gap-0.5">
                        <span className="font-medium">{opt.label}</span>
                        <span className="terminal-kicker !text-[10px]">{opt.detail}</span>
                      </div>
                    </ComboboxItem>
                  ))}
                </ComboboxList>
              </ComboboxContent>
            </Combobox>
          </div>
        )}

        {isLoading ? (
          <div className="flex min-h-[510px] flex-col items-center justify-center gap-5 border border-border bg-card" role="status" aria-live="polite">
            <WaveLoader className="" primaryBgClass="" />
            <p className="terminal-kicker">PROCESSING / {mode === "batch" ? "BATCH FORECASTS" : "SINGLE FORECAST"}</p>
          </div>
        ) : error ? (
          <div className="relative flex min-h-[510px] flex-col items-center justify-center gap-5 border border-destructive/50 bg-card px-6 text-center" role="alert">
            <Button variant="ghost" size="icon-sm" onClick={clearError} className="absolute right-4 top-4 text-destructive" aria-label="Dismiss prediction error">
              <HugeiconsIcon icon={CancelCircleIcon} size={17} strokeWidth={1.5} />
            </Button>
            <HugeiconsIcon icon={Alert02Icon} size={35} strokeWidth={1.3} className="text-destructive" />
            <div className="max-w-md space-y-3">
              <span className="terminal-kicker text-destructive">PREDICTION ERROR</span>
              <h4 className="terminal-heading text-3xl">{error.title}</h4>
              <p className="text-sm leading-relaxed text-muted-foreground">{error.message}</p>
              {error.code && <p className="terminal-mono text-xs text-destructive">{error.code}</p>}
              <p className="terminal-mono text-[11px] text-muted-foreground">{error.timestamp.toLocaleTimeString()}</p>
            </div>
          </div>
        ) : hasResult ? (
          <div className="min-w-0 space-y-7">
            <div className="min-w-0 border border-border bg-card p-3 sm:p-5">
              <PredictionChart ref={chartRef} data={displayResult} />
            </div>
            <ModelComparisonPanel comparisons={displayResult.model_comparisons ?? []} />
          </div>
        ) : (
          <div className="relative flex min-h-[510px] flex-col items-center justify-center overflow-hidden border border-border bg-card px-6 text-center">
            <span aria-hidden="true" className="pointer-events-none absolute bottom-0 right-3 select-none font-sans text-[clamp(9rem,19vw,17rem)] font-black leading-[0.8] tracking-[-0.09em] text-foreground/[0.025]">00</span>
            <span className="terminal-mono absolute left-5 top-5 text-[11px] text-muted-foreground">FIG. 001 / STANDBY</span>
            <span className="terminal-mono absolute right-5 top-5 text-[11px] text-muted-foreground">NO DATA</span>
            <div className="relative z-10 flex flex-col items-center">
              <div className="mb-7 flex size-16 items-center justify-center border border-[#FF3D00]/60 text-[#FF3D00]">
                <HugeiconsIcon icon={ChartCandlestickIcon} size={30} strokeWidth={1.2} />
              </div>
              <span className="terminal-kicker text-[#FF3D00]">AWAITING INPUT</span>
              <h4 className="terminal-heading mt-3 text-[clamp(2rem,4vw,3.75rem)]">NO SIGNAL<br />JUST YET<span className="terminal-accent">.</span></h4>
              <p className="mt-5 max-w-[350px] text-sm leading-relaxed text-muted-foreground">Configure your parameters and run a forecast to populate this canvas.</p>
            </div>
            <div className="absolute inset-x-5 bottom-5 flex justify-between border-t border-border pt-3">
              <span className="terminal-kicker !text-[9px]">HISTORY / FORECAST</span>
              <span className="terminal-kicker !text-[9px]">STUDIO IDLE</span>
            </div>
          </div>
        )}
      </div>
    </section>
  );
};

export default Dashboard;
