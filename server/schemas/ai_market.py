"""Direct market-candle analysis; no forecast or client-selected LLM is required."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class MarketAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,31}$")
    interval: Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"] = "5m"
    lookback: int = Field(default=200, ge=35, le=999)
    data_source: Literal["binance", "yfinance"] = "binance"
    period: Literal["1mo", "3mo", "1y", "2y", "5y", "max"] = "1mo"
    mode: Literal["single", "agents"] = "single"
