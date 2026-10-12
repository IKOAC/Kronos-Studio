"""Deterministic financial calculations: input validation, golden values, and API."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from main import app
from schemas.financial_analysis import (
    FinancialAnalysisRequest,
    FinancialAnalysisResponse,
    ForecastInput,
    MarketCandle,
    TradeInput,
)
from services.financial_analysis.engine import (
    analyze_financials,
    forecast_metrics,
    technical_metrics,
    trade_metrics,
)


def candles(closes, *, volume=10, high_spread=1, low_spread=1):
    start = datetime(2026, 1, 1)
    return [
        MarketCandle(
            timestamps=start + timedelta(hours=i),
            open=float(price),
            high=float(price) + high_spread,
            low=float(price) - low_spread,
            close=float(price),
            volume=volume,
        )
        for i, price in enumerate(closes)
    ]


def trade(**overrides):
    kwargs = {
        "side": "long",
        "entry": 100,
        "stop": 97,
        "target": 106,
        "account_equity": 1000,
        "risk_percent": 1,
        "quantity_step": 0.01,
    }
    kwargs.update(overrides)
    return TradeInput(**kwargs)


def test_short_history_does_not_fabricate_indicator_values():
    r = technical_metrics(candles([100, 101]))
    for key in (
        "sma_20",
        "sma_50",
        "sma_200",
        "ema_12",
        "ema_20",
        "ema_26",
        "ema_50",
        "rsi_14",
        "macd_12_26",
        "macd_signal_9",
        "macd_histogram",
        "atr_14",
        "bollinger_upper_20",
        "volume_ratio_20",
    ):
        assert r[key] is None, key


def test_rsi_neutral_and_atr_constant_market():
    r = technical_metrics(candles([100] * 60))
    assert r["rsi_14"] == 50
    assert r["atr_14"] == pytest.approx(2.0)
    assert r["sma_20"] == pytest.approx(100)
    assert r["sma_50"] == pytest.approx(100)
    assert r["macd_12_26"] == pytest.approx(0)
    assert r["macd_signal_9"] == pytest.approx(0)
    assert r["macd_histogram"] == pytest.approx(0)
    assert r["bollinger_lower_20"] == pytest.approx(100)
    assert r["bollinger_upper_20"] == pytest.approx(100)
    assert r["volume_ratio_20"] == pytest.approx(1)


@pytest.mark.parametrize(
    ("close", "expected"),
    [(list(range(100, 115)), 100), (list(range(114, 99, -1)), 0), ([100] * 15, 50)],
)
def test_rsi_wilder_extremes(close, expected):
    assert technical_metrics(candles(close))["rsi_14"] == pytest.approx(expected)


def test_rsi_seed_uses_14_differences_not_14_prices():
    assert technical_metrics(candles(list(range(100, 114))))["rsi_14"] is None
    assert technical_metrics(candles(list(range(100, 115))))["rsi_14"] is not None


def test_macd_signal_requires_34_candles():
    assert technical_metrics(candles([100] * 33))["macd_signal_9"] is None
    assert technical_metrics(candles([100] * 34))["macd_signal_9"] == pytest.approx(0)


def test_wilder_atr_gap_uses_previous_close():
    series = candles([100] * 13 + [120])
    r = technical_metrics(series)
    # 13 true ranges of 2, then 21 (high=121 vs prior close=100).
    assert r["atr_14"] == pytest.approx((13 * 2 + 21) / 14)


def test_bollinger_population_std_and_volume_ratio():
    r = technical_metrics(candles([100] * 19 + [120], volume=10))
    expected_std = (19 * (100 - 101) ** 2 + (120 - 101) ** 2) / 20
    assert r["bollinger_middle_20"] == pytest.approx(101)
    assert r["bollinger_upper_20"] == pytest.approx(101 + 2 * expected_std**0.5)
    assert r["bollinger_lower_20"] == pytest.approx(101 - 2 * expected_std**0.5)


def test_volume_ratio_not_produced_from_all_zero_volume():
    assert technical_metrics(candles([100] * 30, volume=0))["volume_ratio_20"] is None


def test_sma_200_requires_full_window():
    assert technical_metrics(candles([100] * 199))["sma_200"] is None
    assert technical_metrics(candles([100] * 200))["sma_200"] == pytest.approx(100)


def test_forecast_2_models_disagree_and_not_confidence_probability():
    result = forecast_metrics(
        100,
        [
            ForecastInput(model_name="kronos-mini", final_close=102),
            ForecastInput(model_name="chronos-2", final_close=98),
        ],
    )
    assert result["direction_counts"] == {"up": 1, "down": 1, "flat": 0}
    assert result["majority_direction"] is None
    assert result["agreement_pct"] == 50.0
    assert result["mean_change_pct"] == pytest.approx(0)
    assert result["dispersion_std_pct"] == pytest.approx(2)
    assert result["change_range_pct"] == pytest.approx(4)


def test_forecast_consensus_and_threshold():
    result = forecast_metrics(
        100,
        [
            ForecastInput(model_name="kronos-mini", final_close=102),
            ForecastInput(model_name="chronos-2", final_close=101),
            ForecastInput(model_name="timesfm-2.5", final_close=99),
            ForecastInput(model_name="fincast", final_close=100.05),
        ],
    )
    assert result["direction_counts"] == {"up": 2, "down": 1, "flat": 1}
    assert result["majority_direction"] == "up"
    assert result["agreement_pct"] == pytest.approx(50)


def test_one_forecast_not_cross_model_agreement():
    result = forecast_metrics(100, [ForecastInput(model_name="only", final_close=99)])
    assert result["majority_direction"] is None
    assert result["agreement_pct"] is None
    assert result["dispersion_std_pct"] == 0


def test_absent_forecasts():
    assert forecast_metrics(100, []) is None


def test_long_risk_reward_without_costs():
    r = trade_metrics(trade())
    assert r["loss_per_unit_including_costs"] == pytest.approx(3)
    assert r["profit_per_unit_after_costs"] == pytest.approx(6)
    assert r["net_reward_to_risk"] == pytest.approx(2)
    assert r["break_even_win_rate_pct"] == pytest.approx(100 / 3)
    assert r["risk_budget"] == pytest.approx(10)
    assert r["quantity"] == pytest.approx(3.33)
    assert r["planned_stop_loss"] == pytest.approx(9.99)
    assert r["planned_target_profit"] == pytest.approx(19.98)
    assert r["stop_loss_guaranteed"] is False


def test_short_risk_reward_and_position_sizing():
    r = trade_metrics(
        trade(
            side="short",
            entry=250,
            stop=260,
            target=230,
            account_equity=5000,
            risk_percent=1,
            quantity_step=1,
        )
    )
    assert r["loss_per_unit_including_costs"] == pytest.approx(10)
    assert r["profit_per_unit_after_costs"] == pytest.approx(20)
    assert r["net_reward_to_risk"] == pytest.approx(2)
    assert r["quantity"] == 5
    assert r["planned_stop_loss"] == 50


def test_position_sizing_enforces_no_leverage_buying_power():
    r = trade_metrics(
        trade(entry=65100, stop=64500, target=66900, quantity_step=0.000001)
    )
    assert r["quantity"] == pytest.approx(0.01536)
    assert r["required_entry_notional_and_fee"] <= 1000
    assert r["planned_stop_loss"] <= 10


def test_fees_and_slippage_affect_both_entry_and_exit():
    r = trade_metrics(trade(fee_bps=10, slippage_bps=20))
    expected_entry = Decimal("100.2")
    expected_stop = Decimal("96.806")
    expected_target = Decimal("105.788")
    expected_loss = (
        expected_entry
        - expected_stop
        + Decimal(".001") * (expected_entry + expected_stop)
    )
    expected_profit = (
        expected_target
        - expected_entry
        - Decimal(".001") * (expected_entry + expected_target)
    )
    assert r["assumed_entry_fill"] == pytest.approx(float(expected_entry))
    assert r["assumed_stop_fill"] == pytest.approx(float(expected_stop))
    assert r["assumed_target_fill"] == pytest.approx(float(expected_target))
    assert r["loss_per_unit_including_costs"] == pytest.approx(float(expected_loss))
    assert r["profit_per_unit_after_costs"] == pytest.approx(float(expected_profit))
    assert r["net_reward_to_risk"] == pytest.approx(
        float(expected_profit / expected_loss)
    )
    assert r["planned_stop_loss"] <= r["risk_budget"]
    assert r["required_entry_notional_and_fee"] <= r["exposure_budget"]


def test_short_execution_costs_are_adverse():
    r = trade_metrics(
        trade(
            side="short",
            entry=250,
            stop=260,
            target=230,
            account_equity=5000,
            risk_percent=1,
            fee_bps=10,
            slippage_bps=20,
        )
    )
    assert r["assumed_entry_fill"] < 250
    assert r["assumed_stop_fill"] > 260
    assert r["assumed_target_fill"] > 230
    assert r["loss_per_unit_including_costs"] > 10
    assert r["profit_per_unit_after_costs"] < 20
    assert r["net_reward_to_risk"] < 2


def test_unprofitable_net_target_returns_no_break_even_win_rate():
    r = trade_metrics(
        trade(entry=100, stop=99, target=100.01, fee_bps=100, slippage_bps=50)
    )
    assert r["profit_per_unit_after_costs"] < 0
    assert r["break_even_win_rate_pct"] is None


def test_quantity_is_always_rounded_down_to_step_and_may_be_zero():
    r = trade_metrics(trade(quantity_step=10))
    assert r["quantity"] == 0
    assert r["planned_stop_loss"] == 0
    assert r["required_entry_notional_and_fee"] == 0


def test_budget_and_exposure_constraints_over_many_trades():
    for side, entry, stop, target in [
        ("long", 65000, 64000, 68000),
        ("long", 100, 99.9, 101),
        ("short", 250, 265, 240),
        ("short", 5, 6, 4),
    ]:
        r = trade_metrics(
            trade(
                side=side,
                entry=entry,
                stop=stop,
                target=target,
                account_equity=1500,
                risk_percent=0.75,
                quantity_step=0.0001,
                fee_bps=25,
                slippage_bps=40,
                max_exposure_percent=70,
            )
        )
        assert r["planned_stop_loss"] <= r["risk_budget"] + 1e-9
        assert r["required_entry_notional_and_fee"] <= r["exposure_budget"] + 1e-9


@pytest.mark.parametrize(
    "overrides",
    [
        {"side": "long", "stop": 110},
        {"side": "long", "target": 90},
        {"side": "short", "stop": 90},
        {"side": "short", "target": 110},
        {"risk_percent": 0},
        {"risk_percent": 101},
        {"fee_bps": -1},
        {"slippage_bps": 1001},
        {"quantity_step": 0},
        {"account_equity": 0},
        {"entry": float("nan")},
    ],
)
def test_invalid_trades_rejected_before_calculation(overrides):
    with pytest.raises(ValidationError):
        trade(**overrides)


@pytest.mark.parametrize(
    "bad",
    [
        {"open": 100, "close": 110, "high": 105, "low": 95},
        {"open": 100, "close": 90, "high": 101, "low": 92},
        {"open": 100, "close": 100, "high": 99, "low": 98},
        {"open": -1},
        {"close": float("inf")},
        {"volume": -10},
    ],
)
def test_bad_candles_rejected(bad):
    base = {
        "timestamps": "2026-01-01T00:00:00",
        "open": 100,
        "high": 101,
        "low": 99,
        "close": 100,
        "volume": 10,
    }
    base.update(bad)
    with pytest.raises(ValidationError):
        MarketCandle(**base)


def test_timestamp_ordering_and_duplicate_model_names_rejected():
    history = candles([100, 101])
    with pytest.raises(ValidationError, match="strictly increasing"):
        FinancialAnalysisRequest(history=list(reversed(history)))
    with pytest.raises(ValidationError, match="strictly increasing"):
        FinancialAnalysisRequest(history=[history[0], history[0]])
    with pytest.raises(ValidationError, match="only once"):
        FinancialAnalysisRequest(
            history=history,
            forecasts=[
                ForecastInput(model_name="one", final_close=101),
                ForecastInput(model_name="one", final_close=102),
            ],
        )


def test_exact_data_contract_accepts_kronos_history_amount_field():
    rows = [dict(x.model_dump(mode="json"), amount=1000.0) for x in candles([100] * 40)]
    response = FinancialAnalysisResponse.model_validate(
        analyze_financials(FinancialAnalysisRequest(history=rows))
    )
    assert response.forecast is None
    assert response.trade is None
    assert response.technical.rsi_14 == 50


def test_http_metrics_endpoint_and_schema():
    history = [x.model_dump(mode="json") for x in candles([100] * 40)]
    body = {
        "history": history,
        "forecasts": [
            {"model_name": "kronos-mini", "final_close": 102},
            {"model_name": "chronos-2", "final_close": 98},
        ],
        "trade": trade().model_dump(),
    }
    response = TestClient(app).post("/api/analysis/metrics", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["technical"]["rsi_14"] == 50
    assert data["forecast"]["majority_direction"] is None
    assert data["trade"]["net_reward_to_risk"] == pytest.approx(2)
    assert data["trade"]["planned_stop_loss"] == pytest.approx(9.99)


def test_http_rejects_invalid_price_and_empty_history():
    base = [x.model_dump(mode="json") for x in candles([100] * 20)]
    client = TestClient(app)
    assert client.post("/api/analysis/metrics", json={"history": []}).status_code == 422
    base[0]["low"] = 105
    assert (
        client.post("/api/analysis/metrics", json={"history": base}).status_code == 422
    )
