"""Load completed market candles and analyze them without invoking a model forecast."""

from datetime import datetime, timezone
import pandas as pd
from errors.errors import InsufficientDataError, UnsupportedPredictionOptionError
from schemas.ai_market import MarketAnalysisRequest
from schemas.groq_analysis import GroqAnalysisRequest
from schemas.trading_agents import TradingAgentsRequest
from services.ai_providers import ProviderAnalysisService
from services.raw_data_service.ohlcv_data import OHLCVDataService
from services.trading_agents import TradingAgentsService


class MarketAnalysisService:
    def __init__(self, data=None, ai=None):
        self.data = data or OHLCVDataService()
        self.ai = ai or ProviderAnalysisService()

    def analyze(self, request: MarketAnalysisRequest):
        symbol = request.symbol.upper()
        if request.data_source == "binance":
            prepared = self.data.get_data_from_binance(
                symbol=symbol,
                interval=request.interval,
                lookback=request.lookback,
                pred_len=1,
                limit=request.lookback,
            )
        else:
            if request.interval == "4h":
                raise UnsupportedPredictionOptionError(
                    "Yahoo Finance does not provide the selected interval."
                )
            prepared = self.data.get_data_from_yfinance(
                symbol=symbol,
                interval="1wk" if request.interval == "1w" else request.interval,
                period=request.period,
                lookback=request.lookback + 1,
                pred_len=1,
            )
        frame = prepared["df"].copy()
        stamps = pd.to_datetime(frame["timestamps"], utc=True)
        units = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
        seconds = int(request.interval[:-1]) * units[request.interval[-1]]
        frame = frame[
            stamps + pd.Timedelta(seconds=seconds) <= pd.Timestamp.now(tz="UTC")
        ].tail(request.lookback)
        if len(frame) < request.lookback:
            raise InsufficientDataError(
                "Not enough completed candles. Increase the history period or reduce the candle count.",
                details={
                    "required_rows": request.lookback,
                    "available_rows": len(frame),
                },
            )
        rows = []
        for record in frame.to_dict("records"):
            rows.append(
                {
                    "timestamps": pd.to_datetime(
                        record["timestamps"], utc=True
                    ).isoformat(),
                    **{
                        key: float(record[key])
                        for key in ("open", "high", "low", "close", "volume")
                    },
                }
            )
        snapshot = {
            "symbol": symbol,
            "interval": request.interval,
            "history": rows,
            "forecasts": [],
        }
        if request.mode == "agents":
            result = TradingAgentsService(self.ai).analyze(
                TradingAgentsRequest.model_validate(snapshot)
            )
        else:
            result = self.ai.analyze(GroqAnalysisRequest.model_validate(snapshot))
        result["market_data"] = {
            "data_source": request.data_source,
            "candles": len(rows),
            "first_timestamp": rows[0]["timestamps"],
            "last_timestamp": rows[-1]["timestamps"],
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        return result
