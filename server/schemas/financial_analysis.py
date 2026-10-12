from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MarketCandle(BaseModel):
    """A chronologically ordered, closed OHLCV candle."""

    timestamps: datetime
    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)
    volume: float = Field(default=0.0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_prices(self):
        if self.low > min(self.open, self.close) or self.high < max(
            self.open, self.close
        ):
            raise ValueError("OHLC candle high/low must contain both open and close.")
        if self.low > self.high:
            raise ValueError("Candle low cannot exceed high.")
        return self


class ForecastInput(BaseModel):
    """A model's final-horizon closing price, not an accuracy estimate."""

    model_name: str = Field(min_length=1, max_length=120)
    final_close: float = Field(gt=0, allow_inf_nan=False)


class TradeInput(BaseModel):
    """A proposed trade for deterministic evaluation, not execution."""

    side: Literal["long", "short"]
    entry: float = Field(gt=0, allow_inf_nan=False)
    stop: float = Field(gt=0, allow_inf_nan=False)
    target: float = Field(gt=0, allow_inf_nan=False)
    account_equity: float = Field(gt=0, allow_inf_nan=False)
    risk_percent: float = Field(gt=0, le=100, allow_inf_nan=False)
    fee_bps: float = Field(default=0, ge=0, le=1000, allow_inf_nan=False)
    slippage_bps: float = Field(default=0, ge=0, le=1000, allow_inf_nan=False)
    quantity_step: float = Field(default=0.000001, gt=0, allow_inf_nan=False)
    max_exposure_percent: float = Field(default=100, gt=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_direction(self):
        if self.side == "long" and not (self.stop < self.entry < self.target):
            raise ValueError("For a long trade, stop < entry < target is required.")
        if self.side == "short" and not (self.target < self.entry < self.stop):
            raise ValueError("For a short trade, target < entry < stop is required.")
        return self


class FinancialAnalysisRequest(BaseModel):
    """Closed market candles in chronological order, with optional forecasts/trade."""

    history: list[MarketCandle] = Field(min_length=2, max_length=10_000)
    forecasts: list[ForecastInput] = Field(default_factory=list, max_length=20)
    trade: TradeInput | None = None

    @model_validator(mode="after")
    def validate_history(self):
        def as_utc(ts: datetime) -> datetime:
            return (
                ts.replace(tzinfo=timezone.utc)
                if ts.tzinfo is None
                else ts.astimezone(timezone.utc)
            )

        last_ts: datetime | None = None
        for candle in self.history:
            current = as_utc(candle.timestamps)
            if last_ts is not None and current <= last_ts:
                raise ValueError(
                    "History timestamps must be strictly increasing with no duplicates."
                )
            last_ts = current
        names = [item.model_name for item in self.forecasts]
        if len(set(names)) != len(names):
            raise ValueError("Each model_name may appear only once.")
        return self


class TechnicalMetrics(BaseModel):
    """Latest candle-aligned values; null means insufficient warm-up data."""

    candles: int
    last_close: float
    sma_20: float | None
    sma_50: float | None
    sma_200: float | None
    ema_12: float | None
    ema_20: float | None
    ema_26: float | None
    ema_50: float | None
    rsi_14: float | None
    macd_12_26: float | None
    macd_signal_9: float | None
    macd_histogram: float | None
    atr_14: float | None
    bollinger_middle_20: float | None
    bollinger_upper_20: float | None
    bollinger_lower_20: float | None
    volume_ratio_20: float | None


class ForecastMetric(BaseModel):
    model_name: str
    final_close: float
    change_pct: float
    direction: Literal["up", "down", "flat"]


class ForecastMetrics(BaseModel):
    models: list[ForecastMetric]
    direction_counts: dict[str, int]
    majority_direction: Literal["up", "down", "flat"] | None
    agreement_pct: float | None
    mean_change_pct: float
    median_change_pct: float
    dispersion_std_pct: float
    change_range_pct: float


class TradeMetrics(BaseModel):
    side: Literal["long", "short"]
    assumed_entry_fill: float
    assumed_stop_fill: float
    assumed_target_fill: float
    loss_per_unit_including_costs: float
    profit_per_unit_after_costs: float
    net_reward_to_risk: float
    break_even_win_rate_pct: float | None
    risk_budget: float
    exposure_budget: float
    quantity: float
    planned_stop_loss: float
    planned_target_profit: float
    required_entry_notional_and_fee: float
    stop_loss_guaranteed: bool = False


class FinancialAnalysisResponse(BaseModel):
    technical: TechnicalMetrics
    forecast: ForecastMetrics | None
    trade: TradeMetrics | None
