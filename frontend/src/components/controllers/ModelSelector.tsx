"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ExternalLink } from "lucide-react";
import { getPredictionOptions } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { usePricePredictionStore } from "@/stores/pricePredictionStore";
import { type ModelName } from "@/schemas/predictionSchema";

export default function ModelSelector() {
  const mode = usePricePredictionStore((state) => state.mode);
  const single = usePricePredictionStore((state) => state.params);
  const batch = usePricePredictionStore((state) => state.batchParams);
  const setSingle = usePricePredictionStore((state) => state.setParams);
  const setBatch = usePricePredictionStore((state) => state.setBatchParams);
  const isLoading = usePricePredictionStore((state) => state.isLoading);
  const params = mode === "single" ? single : batch;
  const setParams = mode === "single" ? setSingle : setBatch;
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["prediction-options"], queryFn: getPredictionOptions, staleTime: 60_000,
  });
  const models = data?.models ?? {};
  const primary = models[params.model_name]?.name ?? params.model_name;

  function toggleModel(name: ModelName) {
    const selected = params.selected_models.includes(name)
      ? params.selected_models.filter((model) => model !== name)
      : [...params.selected_models, name];
    if (!selected.length) return;
    const model_ids = { ...params.model_ids };
    if (!selected.includes(name)) delete model_ids[name];
    const needsCpu = params.device === "mps" && selected.some((key) => !models[key]?.devices.includes("mps"));
    setParams({ selected_models: selected, model_ids,
      model_name: selected.includes(params.model_name) ? params.model_name : selected[0],
      ...(needsCpu ? { device: "cpu" as const } : {}),
    });
  }

  return (
    <details className="group w-full min-w-0 rounded-md border bg-background/30">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-3 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0">
          <span className="block text-sm font-semibold">Choose models <span className="text-muted-foreground">({params.selected_models.length})</span></span>
          <span className="block truncate text-xs text-muted-foreground">Primary chart: {primary}</span>
        </span>
        <ChevronDown className="size-4 shrink-0 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div className="space-y-3 border-t p-3">
        <p className="text-xs text-muted-foreground">Check the models to run, then choose your primary chart. New weights download on first use.</p>
        {isPending && <p className="text-xs" role="status">Loading models…</p>}
        {error && <div className="text-xs" role="alert">Could not load models. Check that the backend is running. <button type="button" className="underline" onClick={() => refetch()}>Retry</button></div>}
        <fieldset disabled={isLoading} className="space-y-2 disabled:opacity-60">
          <legend className="sr-only">Models included in this prediction</legend>
          {Object.entries(models).map(([key, model]) => {
            if (!model) return null;
            const name = key as ModelName;
            const selected = params.selected_models.includes(name);
            return <div key={name} className={`min-w-0 rounded border p-3 ${selected ? "border-primary/50 bg-muted/30" : "border-border"}`}>
              <div className="flex items-center justify-between gap-2">
                <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
                  <input type="checkbox" checked={selected} onChange={() => toggleModel(name)} disabled={selected && params.selected_models.length === 1} className="size-4 accent-primary" />
                  {model.name}
                </label>
                <span className="text-xs text-muted-foreground">{model.params}</span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{model.description}</p>
              <p className="mt-1 text-xs text-muted-foreground">{model.output_type === "close" ? "Price line · CPU / CUDA" : "Candles · CPU / CUDA / MPS"}</p>
              {selected ? <div className="mt-3 space-y-2">
                <label className="flex cursor-pointer items-center gap-2 text-xs">
                  <input type="radio" name={`primary-model-${mode}`} checked={params.model_name === name} onChange={() => setParams({ model_name: name })} className="accent-primary" />
                  Primary chart model
                </label>
                <label htmlFor={`model-id-${name}`} className="block text-xs text-muted-foreground">Hugging Face ID</label>
                <Input id={`model-id-${name}`} value={params.model_ids[name] ?? model.model_id} spellCheck={false}
                  onChange={(event) => setParams({ model_ids: { ...params.model_ids, [name]: event.target.value } })}
                  className="h-8 w-full min-w-0 text-xs" />
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                  <a href={`https://huggingface.co/${model.model_id}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline">Official checkpoint <ExternalLink className="size-3" /></a>
                  {params.model_ids[name] !== undefined && <button type="button" className="underline" onClick={() => {
                    const ids = { ...params.model_ids }; delete ids[name]; setParams({ model_ids: ids });
                  }}>Reset ID</button>}
                </div>
              </div> : <p className="mt-2 break-all font-mono text-xs text-muted-foreground">{model.model_id}</p>}
            </div>;
          })}
        </fieldset>
        <p className="text-xs text-muted-foreground">Custom IDs must use the same model architecture. Kronos checkpoints must also match the original tokenizer. FinCast uses a v1.pth checkpoint.</p>
      </div>
    </details>
  );
}
