import type { ModelComparison } from "@/schemas/predictionSchema";

type ModelComparisonPanelProps = {
  comparisons: ModelComparison[];
};

const directionLabel: Record<ModelComparison["direction"], string> = {
  up: "UPWARD",
  down: "DOWNWARD",
  flat: "FLAT",
};

function formatChange(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export default function ModelComparisonPanel({ comparisons }: ModelComparisonPanelProps) {
  if (comparisons.length === 0) return null;

  return (
    <section className="border-t border-border pt-7" aria-labelledby="comparison-heading">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <span className="terminal-kicker"><span className="terminal-accent">03</span> / CROSS-EXAMINE</span>
          <h4 id="comparison-heading" className="terminal-heading mt-3 text-2xl sm:text-3xl">MODEL COMPARISON<span className="terminal-accent">.</span></h4>
        </div>
        <span className="terminal-mono border-b border-[#FF3D00] pb-2 text-[11px] text-[#FF3D00]">
          {String(comparisons.length).padStart(2, "0")} MODELS
        </span>
      </div>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
        Directional consensus describes agreement between models, not the probability that a forecast will be correct.
      </p>
      <div className="mt-6 grid grid-cols-1 gap-px border border-border bg-border sm:grid-cols-2 2xl:grid-cols-3">
        {comparisons.map((item, index) => (
          <article key={item.model_name} className="min-w-0 bg-background p-5 sm:p-6">
            <div className="flex items-center justify-between gap-3">
              <span className="terminal-kicker">FORECAST / {String(index + 1).padStart(2, "0")}</span>
              <span className="terminal-mono text-[11px] text-muted-foreground">{directionLabel[item.direction]}</span>
            </div>
            <h5 className="mt-5 truncate font-sans text-xl font-extrabold tracking-[-0.05em]" title={item.model.name}>{item.model.name}</h5>
            <p className="terminal-mono mt-1 truncate text-[10px] text-muted-foreground" title={item.model.model_id}>{item.model.model_id}</p>
            <div className="mt-7 flex flex-wrap items-end justify-between gap-3 border-b border-border pb-5">
              <div>
                <p className="terminal-kicker !text-[9px]">FORECAST CHANGE</p>
                <p className="terminal-mono mt-2 text-2xl font-bold tracking-[-0.04em]">{formatChange(item.predicted_change_pct)}</p>
              </div>
              <div className="text-right">
                <p className="terminal-kicker !text-[9px]">AGREEMENT</p>
                <p className="terminal-mono mt-2 text-2xl font-bold tracking-[-0.04em] text-[#FF3D00]">
                  {comparisons.length > 1 ? `${item.confidence_score.toFixed(0)}%` : "—"}
                </p>
              </div>
            </div>
            <div className="mt-5 h-1 w-full bg-muted" role="img" aria-label={`Directional agreement: ${item.confidence_score.toFixed(0)} percent`}>
              <div className="h-full bg-[#FF3D00]" style={{ width: `${Math.max(0, Math.min(100, item.confidence_score))}%` }} />
            </div>
            <p className="terminal-kicker mt-3 !text-[9px]">{item.confidence_label}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
