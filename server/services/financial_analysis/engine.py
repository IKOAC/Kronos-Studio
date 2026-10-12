"""Deterministic, read-only financial calculations.

No network, LLM, exchange execution, price prediction, or side effects.
Indicators use only closed input candles supplied in chronological order.
"""

from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal
from statistics import fmean, median, pstdev

import numpy as np
import pandas as pd

from schemas.financial_analysis import (
    FinancialAnalysisRequest,
    ForecastInput,
    MarketCandle,
    TradeInput,
)


def _last_finite(series: pd.Series) -> float | None:
    value = float(series.iloc[-1])
    return value if np.isfinite(value) else None


def _wilder_rsi(close: np.ndarray, period: int = 14) -> float | None:
    """Wilder RSI: seed from first period differences, then recursive smoothing."""
    if len(close) < period + 1:
        return None

    changes = np.diff(close)
    gains = np.maximum(changes, 0.0)
    losses = np.maximum(-changes, 0.0)
    average_gain = float(np.mean(gains[:period]))
    average_loss = float(np.mean(losses[:period]))
    for i in range(period, len(changes)):
        average_gain = ((period - 1) * average_gain + gains[i]) / period
        average_loss = ((period - 1) * average_loss + losses[i]) / period

    if average_gain == 0 and average_loss == 0:
        return 50.0  # No change; neutral by convention.
    if average_loss == 0:
        return 100.0
    ratio = average_gain / average_loss
    return float(100.0 - 100.0 / (1.0 + ratio))


def _wilder_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14
) -> float | None:
    """Wilder ATR: first TR = high-low; first ATR = mean of initial 14 TRs."""
    count = len(close)
    if count < period:
        return None

    previous_close = np.r_[close[0], close[:-1]]
    true_range = np.maximum.reduce(
        (high - low, np.abs(high - previous_close), np.abs(low - previous_close))
    )
    atr = float(np.mean(true_range[:period]))
    for tr in true_range[period:]:
        atr = ((period - 1) * atr + float(tr)) / period
    return atr


def technical_metrics(history: list[MarketCandle]) -> dict:
    """Return latest technical metrics. Insufficient warm-up stays null, not zero."""
    close = np.fromiter(
        (c.close for c in history), dtype=np.float64, count=len(history)
    )
    high = np.fromiter((c.high for c in history), dtype=np.float64, count=len(history))
    low = np.fromiter((c.low for c in history), dtype=np.float64, count=len(history))
    volume = np.fromiter(
        (c.volume for c in history), dtype=np.float64, count=len(history)
    )
    series = pd.Series(close, copy=False)

    def sma(period: int) -> float | None:
        return float(np.mean(close[-period:])) if len(close) >= period else None

    def ema(period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False, min_periods=period).mean()

    ema_12 = ema(12)
    ema_20 = ema(20)
    ema_26 = ema(26)
    ema_50 = ema(50)

    macd = ema_12 - ema_26
    signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    macd_value = _last_finite(macd)
    signal_value = _last_finite(signal)

    middle = sma(20)
    if middle is not None:
        std = float(np.std(close[-20:], ddof=0))
        upper, lower = middle + 2 * std, middle - 2 * std
        mean_volume = float(np.mean(volume[-20:]))
        volume_ratio = float(volume[-1] / mean_volume) if mean_volume > 0 else None
    else:
        upper = lower = volume_ratio = None

    return {
        "candles": len(close),
        "last_close": float(close[-1]),
        "sma_20": middle,
        "sma_50": sma(50),
        "sma_200": sma(200),
        "ema_12": _last_finite(ema_12),
        "ema_20": _last_finite(ema_20),
        "ema_26": _last_finite(ema_26),
        "ema_50": _last_finite(ema_50),
        "rsi_14": _wilder_rsi(close),
        "macd_12_26": macd_value,
        "macd_signal_9": signal_value,
        "macd_histogram": (
            macd_value - signal_value
            if macd_value is not None and signal_value is not None
            else None
        ),
        "atr_14": _wilder_atr(high, low, close),
        "bollinger_middle_20": middle,
        "bollinger_upper_20": upper,
        "bollinger_lower_20": lower,
        "volume_ratio_20": volume_ratio,
    }


def forecast_metrics(last_close: float, forecasts: list[ForecastInput]) -> dict | None:
    """Unweighted forecast changes and population dispersion; never predictive confidence."""
    if not forecasts:
        return None

    models = []
    changes = []
    counts = {"up": 0, "down": 0, "flat": 0}
    for item in forecasts:
        change = (item.final_close / last_close - 1.0) * 100.0
        direction = "up" if change > 0.1 else "down" if change < -0.1 else "flat"
        models.append(
            {
                "model_name": item.model_name,
                "final_close": item.final_close,
                "change_pct": change,
                "direction": direction,
            }
        )
        changes.append(change)
        counts[direction] += 1

    highest = max(counts.values())
    most_common = [direction for direction, count in counts.items() if count == highest]
    # A tie or only one model cannot establish cross-model consensus.
    comparable = len(forecasts) > 1
    majority_direction = (
        most_common[0] if comparable and len(most_common) == 1 else None
    )
    agreement_pct = 100.0 * highest / len(forecasts) if comparable else None
    return {
        "models": models,
        "direction_counts": counts,
        "majority_direction": majority_direction,
        "agreement_pct": agreement_pct,
        "mean_change_pct": fmean(changes),
        "median_change_pct": median(changes),
        "dispersion_std_pct": pstdev(changes),
        "change_range_pct": max(changes) - min(changes),
    }


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def trade_metrics(trade: TradeInput) -> dict:
    """Evaluate a hypothetical trade with conservative adverse execution costs.

    No leverage: max notional (including entry fee) <= exposure budget.
    Fees on entry AND exit are included. Slippage is adverse on every fill.
    Quantity is rounded DOWN to the configured step. Stops are NOT guaranteed.
    """
    entry = _decimal(trade.entry)
    stop = _decimal(trade.stop)
    target = _decimal(trade.target)
    equity = _decimal(trade.account_equity)
    fee = _decimal(trade.fee_bps) / Decimal(10_000)
    slip = _decimal(trade.slippage_bps) / Decimal(10_000)
    step = _decimal(trade.quantity_step)

    if trade.side == "long":
        entry_fill = entry * (1 + slip)
        stop_fill = stop * (1 - slip)
        target_fill = target * (1 - slip)
        raw_loss = entry_fill - stop_fill
        raw_profit = target_fill - entry_fill
    else:
        entry_fill = entry * (1 - slip)
        stop_fill = stop * (1 + slip)
        target_fill = target * (1 + slip)
        raw_loss = stop_fill - entry_fill
        raw_profit = entry_fill - target_fill

    loss = raw_loss + fee * (entry_fill + stop_fill)
    profit = raw_profit - fee * (entry_fill + target_fill)
    # Direction validation and adverse fills must always produce positive loss.
    if loss <= 0:
        raise ValueError("Non-positive stop risk after execution assumptions.")

    risk_budget = equity * _decimal(trade.risk_percent) / 100
    exposure_budget = equity * _decimal(trade.max_exposure_percent) / 100
    by_risk = risk_budget / loss
    by_exposure = exposure_budget / (entry_fill * (1 + fee))
    raw_quantity = min(by_risk, by_exposure)
    quantity = (raw_quantity / step).to_integral_value(rounding=ROUND_FLOOR) * step

    return {
        "side": trade.side,
        "assumed_entry_fill": float(entry_fill),
        "assumed_stop_fill": float(stop_fill),
        "assumed_target_fill": float(target_fill),
        "loss_per_unit_including_costs": float(loss),
        "profit_per_unit_after_costs": float(profit),
        "net_reward_to_risk": float(profit / loss),
        "break_even_win_rate_pct": (
            float(100 * loss / (profit + loss)) if profit > 0 else None
        ),
        "risk_budget": float(risk_budget),
        "exposure_budget": float(exposure_budget),
        "quantity": float(quantity),
        "planned_stop_loss": float(loss * quantity),
        "planned_target_profit": float(profit * quantity),
        "required_entry_notional_and_fee": float(entry_fill * quantity * (1 + fee)),
        "stop_loss_guaranteed": False,
    }


def analyze_financials(request: FinancialAnalysisRequest) -> dict:
    """Independent calculations from supplied data; no network or model calls."""
    technical = technical_metrics(request.history)
    return {
        "technical": technical,
        "forecast": forecast_metrics(technical["last_close"], request.forecasts),
        "trade": trade_metrics(request.trade) if request.trade is not None else None,
    }
