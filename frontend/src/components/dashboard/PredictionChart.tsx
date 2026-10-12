import { forwardRef, useState } from "react";
import PriceChart from "@/components/charts/PriceChart";
import TradingViewCandlestickChart from "@/components/charts/TradingViewCandlestickChart";
import LiveForecastOverlayChart from "@/components/charts/LiveForecastOverlayChart";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { useChartUIStore } from "@/stores/chartUIStore";
import { type PricePredictionResponse } from "@/schemas/predictionSchema";

type PredictionChartProps = {
  data: PricePredictionResponse;
};

const PredictionChart = forwardRef<HTMLDivElement, PredictionChartProps>(({ data }, ref) => {
  const showVolume = useChartUIStore((state) => state.showVolume);
  const chartType = useChartUIStore((state) => state.chartType);
  const setShowVolume = useChartUIStore((state) => state.setShowVolume);
  const setChartType = useChartUIStore((state) => state.setChartType);
  const [showLiveOverlay, setShowLiveOverlay] = useState(false);
  const closeOnly = data.model.output_type === "close";
  const canUseLiveOverlay = data.request.data_source === "binance";

  return (
    <div ref={ref} className='flex h-[520px] min-w-0 flex-col md:h-[590px]'>
      <div className='flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4'>
        {!showLiveOverlay && (
          <Tabs
            value={closeOnly ? "line" : chartType}
            onValueChange={(value) => setChartType(value === "candlestick" ? "candlestick" : "line")}
          >
            <TabsList variant='line' className='bg-transparent'>
              <TabsTrigger disabled={closeOnly} value='candlestick' className='min-h-10 cursor-pointer px-4 uppercase tracking-widest data-active:text-[#FF3D00] data-active:after:bg-[#FF3D00]'>
                Candles
              </TabsTrigger>
              <TabsTrigger value='line' className='min-h-10 cursor-pointer px-4 uppercase tracking-widest data-active:text-[#FF3D00] data-active:after:bg-[#FF3D00]'>
                Line
              </TabsTrigger>
            </TabsList>
          </Tabs>
        )}

        <div className='flex flex-wrap items-center gap-3'>
          <div className='flex items-center gap-2' title={canUseLiveOverlay ? "Stream live Binance candles behind the selected forecast lines" : "Live overlay currently supports Binance predictions"}>
            <Switch
              checked={showLiveOverlay}
              onCheckedChange={(checked) => setShowLiveOverlay(checked && canUseLiveOverlay)}
              disabled={!canUseLiveOverlay}
              className='cursor-pointer'
            />
            <span className='terminal-kicker !text-[10px]'>Live overlay</span>
          </div>
          <div className='flex items-center gap-2'>
            <Switch checked={showVolume} onCheckedChange={setShowVolume} className='cursor-pointer' />
            <span className='terminal-kicker !text-[10px]'>Volume</span>
          </div>
        </div>
      </div>
      {closeOnly && <p className='py-3 text-xs leading-relaxed text-muted-foreground'>{data.model.name} forecasts closing prices. Candle highs, lows and volume are not predicted.</p>}
      <div className='min-h-0 flex-1'>
        {showLiveOverlay && canUseLiveOverlay ? (
          <LiveForecastOverlayChart data={data} showVolume={showVolume} />
        ) : chartType === "candlestick" && !closeOnly ? (
          <TradingViewCandlestickChart data={data} showVolume={showVolume} />
        ) : (
          <PriceChart data={data} showVolume={showVolume} />
        )}
      </div>
    </div>
  );
});

PredictionChart.displayName = "PredictionChart";

export default PredictionChart;
