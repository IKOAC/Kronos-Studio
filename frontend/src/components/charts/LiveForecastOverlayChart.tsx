"use client";

import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type CandlestickData,
  type HistogramData,
  type UTCTimestamp
} from "lightweight-charts";
import { type PricePredictionResponse } from "@/schemas/predictionSchema";
import { cn } from "@/lib/utils";

type LiveForecastOverlayChartProps = {
  data: PricePredictionResponse;
  showVolume?: boolean;
};

type ConnectionStatus = "connecting" | "live" | "reconnecting";

type CandleSeriesUpdater = {
  update: (bar: CandlestickData<UTCTimestamp>) => void;
};

const toChartTime = (value: string): UTCTimestamp => {
  // Backend Binance timestamps are naive ISO strings representing UTC. Treat
  // those as UTC too, so historical candles line up with UTC WebSocket times.
  const normalized = value.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`;
  return Math.floor(new Date(normalized).getTime() / 1000) as UTCTimestamp;
};

const modelColors: Record<PricePredictionResponse["request"]["model_name"], string> = {
  "kronos-mini": "#60a5fa",
  "kronos-small": "#c084fc",
  "kronos-base": "#fbbf24"
};

export default function LiveForecastOverlayChart({
  data,
  showVolume = false
}: LiveForecastOverlayChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const candleSeriesRef = useRef<CandleSeriesUpdater | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting");

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const { width, height } = container.getBoundingClientRect();
    const chart = createChart(container, {
      width: Math.max(1, Math.floor(width)),
      height: Math.max(1, Math.floor(height)),
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(255, 255, 255, 0.76)",
        attributionLogo: true
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.05)" },
        horzLines: { color: "rgba(255, 255, 255, 0.08)" }
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.12)",
        scaleMargins: { top: 0.08, bottom: showVolume ? 0.26 : 0.08 }
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.12)",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 6,
        barSpacing: 8
      },
      crosshair: { mode: CrosshairMode.MagnetOHLC },
      localization: { priceFormatter: (price: number) => price.toLocaleString(undefined, { maximumFractionDigits: 8 }) }
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#ef4444",
      borderUpColor: "#10b981",
      borderDownColor: "#ef4444",
      wickUpColor: "#6ee7b7",
      wickDownColor: "#fca5a5",
      lastValueVisible: true,
      priceLineVisible: true
    });
    candles.setData(
      data.history.map((item) => ({
        time: toChartTime(item.timestamps),
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close
      }))
    );
    candleSeriesRef.current = candles;

    const comparisons = data.model_comparisons?.length
      ? data.model_comparisons
      : [
          {
            model_name: data.request.model_name,
            model: data.model,
            prediction: data.prediction
          }
        ];

    comparisons.forEach((comparison) => {
      const color = modelColors[comparison.model_name];
      const forecast = chart.addSeries(LineSeries, {
        color,
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        title: comparison.model.name,
        lastValueVisible: true,
        priceLineVisible: false,
        crosshairMarkerVisible: true
      });
      const historicalAnchor = data.history.at(-1);
      const forecastPoints = comparison.prediction.map((item) => ({
        time: toChartTime(item.timestamps),
        value: item.close
      }));
      forecast.setData(
        historicalAnchor
          ? [
              { time: toChartTime(historicalAnchor.timestamps), value: historicalAnchor.close },
              ...forecastPoints
            ]
          : forecastPoints
      );
    });

    if (showVolume) {
      const volume = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
        lastValueVisible: false,
        priceLineVisible: false
      });
      volume.setData(
        data.history.map(
          (item): HistogramData => ({
            time: toChartTime(item.timestamps),
            value: item.volume,
            color: item.close >= item.open ? "rgba(16, 185, 129, 0.28)" : "rgba(239, 68, 68, 0.28)"
          })
        )
      );
      chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    }

    chart.timeScale().fitContent();
    const resizeObserver = new ResizeObserver(([entry]) => {
      if (!entry) return;
      chart.applyOptions({
        width: Math.max(1, Math.floor(entry.contentRect.width)),
        height: Math.max(1, Math.floor(entry.contentRect.height))
      });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      candleSeriesRef.current = null;
    };
  }, [data, showVolume]);

  useEffect(() => {
    const symbol = data.request.symbol?.trim().toLowerCase();
    const interval = data.request.interval;
    if (!symbol || data.request.data_source !== "binance") return;

    let stopped = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;
    const url = `wss://stream.binance.com:9443/ws/${symbol}@kline_${interval}`;

    const connect = () => {
      if (stopped) return;
      socket = new WebSocket(url);

      socket.onopen = () => {
        if (!stopped) setConnectionStatus("live");
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        try {
          const payload = JSON.parse(event.data);
          const kline = payload?.k;
          const series = candleSeriesRef.current;
          if (!kline || !series) return;

          const open = Number(kline.o);
          const high = Number(kline.h);
          const low = Number(kline.l);
          const close = Number(kline.c);
          if (![open, high, low, close].every(Number.isFinite)) return;

          series.update({
            time: Math.floor(Number(kline.t) / 1000) as UTCTimestamp,
            open,
            high,
            low,
            close
          });
        } catch {
          // Ignore malformed stream messages; a later kline update can recover.
        }
      };

      socket.onerror = () => {
        socket?.close();
      };

      socket.onclose = () => {
        if (stopped) return;
        setConnectionStatus("reconnecting");
        retryTimer = window.setTimeout(connect, 3000);
      };
    };

    connect();
    return () => {
      stopped = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, [data.request.data_source, data.request.symbol, data.request.interval]);

  return (
    <div className="flex h-full min-h-[360px] flex-col border bg-background">
      <div className="flex min-h-10 flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium">{data.request.symbol}</span>
          <span className="text-muted-foreground">{data.request.interval}</span>
          <span className="text-muted-foreground">Live candles + forecast overlays</span>
        </div>
        <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
          <span className={cn("size-2 rounded-full", connectionStatus === "live" ? "bg-emerald-500" : "bg-amber-400")} />
          {connectionStatus === "live" ? "LIVE · Binance stream" : connectionStatus === "connecting" ? "Connecting to Binance…" : "Reconnecting…"}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b px-3 py-2 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full bg-emerald-500" />Live price</span>
        {(data.model_comparisons?.length
          ? data.model_comparisons
          : [{ model_name: data.request.model_name, model: data.model, prediction: data.prediction }]
        ).map((item) => (
          <span key={item.model_name} className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4" style={{ backgroundColor: modelColors[item.model_name] }} />
            {item.model.name} forecast
          </span>
        ))}
      </div>
      <div ref={containerRef} className="min-h-0 flex-1" />
      <p className="border-t px-3 py-2 text-xs text-muted-foreground">
        Forecast paths remain fixed from the prediction run. New Binance candles update live, so the chart lets you compare the forecast with what the market does next.
      </p>
    </div>
  );
}
