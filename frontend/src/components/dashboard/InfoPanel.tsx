import { usePricePredictionStore } from "@/stores/pricePredictionStore";

const modeLabel = (modelName: string) => {
  if (modelName === "kronos-mini") return "FAST";
  if (modelName === "kronos-small") return "BALANCED";
  if (modelName === "kronos-base") return "QUALITY";
  return "CLOSE FORECAST";
};

export default function InfoPanel() {
  const singleParams = usePricePredictionStore((state) => state.params);
  const batchParamsState = usePricePredictionStore((state) => state.batchParams);
  const mode = usePricePredictionStore((state) => state.mode);
  const batchItems = usePricePredictionStore((state) => state.batchItems);
  const batchResults = usePricePredictionStore((state) => state.batchResults);
  const activeResultIndex = usePricePredictionStore((state) => state.activeResultIndex);

  const isBatch = mode === "batch";
  const params = isBatch ? batchParamsState : singleParams;
  const batchSelection = batchResults?.[activeResultIndex]?.request;
  const activeSymbol = isBatch
    ? batchSelection?.symbol || batchItems[0]?.symbol || "NOT SELECTED"
    : params.symbol || "NOT SELECTED";
  const activeDataSource = isBatch
    ? batchSelection?.data_source || batchItems[0]?.data_source || "binance"
    : params.data_source;
  const activeInterval = isBatch
    ? batchSelection?.interval || batchItems[0]?.interval || "1h"
    : params.interval;

  const facts = [
    {
      index: "01",
      label: "SELECTED MARKET",
      value: activeSymbol,
      note: `${activeDataSource?.toUpperCase()} / ${activeInterval?.toUpperCase()}`,
    },
    {
      index: "02",
      label: "FORECAST WINDOW",
      value: `${params.pred_len} STEPS`,
      note: `${params.lookback} CANDLES / LOOKBACK`,
    },
    {
      index: "03",
      label: "COMPUTE DEVICE",
      value: params.device.toUpperCase(),
      note: `${modeLabel(params.model_name)} / ${params.selected_models.length} MODEL${params.selected_models.length === 1 ? "" : "S"}`,
    },
  ];

  return (
    <div className="grid grid-cols-1 border-b border-border sm:grid-cols-3" aria-label="Forecast configuration summary">
      {facts.map((fact, index) => (
        <div key={fact.label} className={`min-w-0 px-5 py-6 sm:px-7 ${index < 2 ? "border-b border-border sm:border-b-0 sm:border-r" : ""}`}>
          <div className="flex items-center gap-2">
            <span className="terminal-section-index">{fact.index}</span>
            <span className="terminal-kicker !text-[9px]">{fact.label}</span>
          </div>
          <p className="mt-3 truncate font-sans text-[clamp(1.25rem,2.1vw,1.9rem)] font-extrabold uppercase leading-none tracking-[-0.055em]" title={fact.value}>
            {fact.value}
          </p>
          <p className="terminal-mono mt-3 truncate text-[10px] tracking-[0.025em] text-muted-foreground">{fact.note}</p>
        </div>
      ))}
    </div>
  );
}
