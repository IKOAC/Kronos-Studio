"use client";

import { toast } from "sonner";

import { useMutation } from "@tanstack/react-query";
import { PlayIcon, RefreshIcon, PlusSignIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";

import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

import DataSelector from "./DataSelector";
import ModelSelector from "./ModelSelector";
import BatchItemCard from "./BatchItemCard";

import { usePricePredictionStore, type PredictionMode } from "@/stores/pricePredictionStore";
import { predictPrice, predictPriceBatch } from "@/lib/api";
import { PredictionApiError } from "@/utils/handleAPI";
import type { PricePredictionRequest } from "@/schemas/predictionSchema";

const MAX_BATCH_SIZE = 20;

const Controllers = () => {
  const params = usePricePredictionStore((state) => state.params);
  const batchParams = usePricePredictionStore((state) => state.batchParams);
  const mode = usePricePredictionStore((state) => state.mode);
  const setMode = usePricePredictionStore((state) => state.setMode);
  const reset = usePricePredictionStore((state) => state.reset);
  const setResult = usePricePredictionStore((state) => state.setResult);
  const setBatchResults = usePricePredictionStore((state) => state.setBatchResults);
  const setIsLoading = usePricePredictionStore((state) => state.setIsLoading);
  const setError = usePricePredictionStore((state) => state.setError);
  const clearError = usePricePredictionStore((state) => state.clearError);
  const batchItems = usePricePredictionStore((state) => state.batchItems);
  const addBatchItem = usePricePredictionStore((state) => state.addBatchItem);
  const setActiveResultIndex = usePricePredictionStore((state) => state.setActiveResultIndex);

  // --- Single prediction mutation ---
  const predictPriceMutation = useMutation({
    mutationFn: predictPrice,
    onSuccess: (data) => {
      setResult(data);
      clearError();
      setIsLoading(false);
    },
    onError: (error) => {
      console.error("Prediction error:", error);
      const apiErr = error instanceof PredictionApiError ? error : null;
      const errTitle = apiErr?.code ? `${apiErr.code} (${apiErr.status})` : `Prediction Failed`;
      const errMessage = apiErr?.message ?? error.message ?? "An unexpected error occurred.";

      setError({ title: errTitle, message: errMessage, code: apiErr?.code, timestamp: new Date() });
      toast.error(errTitle, {
        description: errMessage,
        duration: 6000
      });

      setIsLoading(false);
      setResult(null);
    },
    onMutate: () => {
      setIsLoading(true);
      setResult(null);
      clearError();
    }
  });

  // --- Batch prediction mutation ---
  const predictPriceBatchMutation = useMutation({
    mutationFn: predictPriceBatch,
    onSuccess: (data) => {
      setBatchResults(data);
      setActiveResultIndex(0);
      clearError();
      setIsLoading(false);
    },
    onError: (error) => {
      console.error("Batch prediction error:", error);
      const apiErr = error instanceof PredictionApiError ? error : null;
      const errTitle = apiErr?.code ? `${apiErr.code} (${apiErr.status})` : `Batch Prediction Failed`;
      const errMessage = apiErr?.message ?? error.message ?? "An unexpected error occurred.";

      setError({ title: errTitle, message: errMessage, code: apiErr?.code, timestamp: new Date() });
      toast.error(errTitle, {
        description: errMessage,
        duration: 6000
      });

      setIsLoading(false);
      setBatchResults(null);
    },
    onMutate: () => {
      setIsLoading(true);
      setBatchResults(null);
      clearError();
    }
  });

  const handlePredict = () => {
    if (mode === "single") {
      if (params.data_source === "local" && !params.local_path) {
        toast.error("CSV file required", {
          description: "Upload a CSV file before running a local prediction."
        });
        return;
      }

      predictPriceMutation.mutate(params);
    } else {
      const missingLocalFileIndex = batchItems.findIndex((item) => item.data_source === "local" && !item.local_path);
      if (missingLocalFileIndex >= 0) {
        toast.error("CSV file required", {
          description: `Upload a CSV file for symbol #${missingLocalFileIndex + 1}.`
        });
        return;
      }

      // Merge batch shared params with each batch item's per-item overrides

      const batchRequests: PricePredictionRequest[] = batchItems.map((item) => ({
        ...batchParams, // batch shared: model_name, device, lookback, pred_len
        ...item, // source and sampling settings are per item
        model_name: batchParams.model_name,
        selected_models: batchParams.selected_models,
        model_ids: batchParams.model_ids,
        device: batchParams.device,
        lookback: batchParams.lookback,
        pred_len: batchParams.pred_len
      }));

      predictPriceBatchMutation.mutate(batchRequests);
    }
  };

  const handleReset = () => {
    reset();
    setResult(null);
    setBatchResults(null);
    setIsLoading(false);
  };

  const isPending = mode === "single" ? predictPriceMutation.isPending : predictPriceBatchMutation.isPending;
  const isMissingLocalFile =
    mode === "single"
      ? params.data_source === "local" && !params.local_path
      : batchItems.some((item) => item.data_source === "local" && !item.local_path);

  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="flex flex-1 flex-col gap-7 px-5 py-6 sm:px-6">
        <div className="space-y-3">
          <span className="terminal-kicker">RUN TYPE / 01</span>
          <Tabs value={mode} onValueChange={(value) => setMode(value as PredictionMode)} className="w-full">
            <TabsList variant="line" className="grid h-12 w-full grid-cols-2 gap-0 border-b border-border bg-transparent p-0">
              <TabsTrigger value="single" className="h-12 cursor-pointer text-xs uppercase tracking-widest data-active:text-[#FF3D00] data-active:after:bg-[#FF3D00]">Single</TabsTrigger>
              <TabsTrigger value="batch" className="h-12 cursor-pointer text-xs uppercase tracking-widest data-active:text-[#FF3D00] data-active:after:bg-[#FF3D00]">Batch</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        <div className="space-y-3">
          <span className="terminal-kicker">INFERENCE / 02</span>
          <ModelSelector />
        </div>

        <div className="space-y-3 border-t border-border pt-6">
          <span className="terminal-kicker">MARKET DATA &amp; SETTINGS / 03</span>
          <DataSelector />
        </div>

        {mode === "batch" && (
          <div className="space-y-4 border-t border-border pt-6">
            <div className="flex items-center justify-between gap-2">
              <div>
                <span className="terminal-kicker">BATCH QUEUE / 04</span>
                <p className="terminal-mono mt-1 text-xs text-foreground">{batchItems.length} of {MAX_BATCH_SIZE} markets</p>
              </div>
              <Button variant="outline" size="sm" onClick={addBatchItem} disabled={batchItems.length >= MAX_BATCH_SIZE} className="gap-1.5">
                <HugeiconsIcon icon={PlusSignIcon} size={14} strokeWidth={1.5} /> Add symbol
              </Button>
            </div>
            <div className="flex max-h-[440px] flex-col gap-3 overflow-y-auto pr-1">
              {batchItems.map((item, index) => (
                <BatchItemCard key={index} index={index} item={item} canRemove={batchItems.length > 1} />
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-4 border-t border-border bg-card px-5 py-5 sm:px-6">
        <Button type="button" className="min-w-0 flex-[2] justify-between gap-2 px-0" onClick={handlePredict} disabled={isPending || isMissingLocalFile}>
          <span>{isPending ? "Forecasting…" : mode === "batch" ? `Run batch (${batchItems.length})` : "Run forecast"}</span>
          <HugeiconsIcon icon={PlayIcon} size={16} strokeWidth={1.6} />
        </Button>
        <Button variant="ghost" className="flex-1 px-0" onClick={handleReset} disabled={isPending}>
          <HugeiconsIcon icon={RefreshIcon} size={14} strokeWidth={1.5} /> Reset
        </Button>
      </div>
    </div>
  );
};

export default Controllers;
