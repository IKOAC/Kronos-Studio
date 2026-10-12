"""Exercise three-model orchestration without downloading model weights."""

import pandas as pd

from constants.available_models import DEFAULT_MODELS
from schemas.prediction import PricePredictionRequest, PricePredictionResponse
from services.prediction_service.batch_price_prediction import BatchPricePredictionService
from services.prediction_service.price_prediction import PricePredictionService


class FakeOHLCVSource:
    def get_data_from_binance(self, **kwargs):
        base = 200.0 if kwargs["symbol"] == "BTCUSDT" else 100.0
        timestamps = pd.date_range("2026-01-01T00:00:00", periods=2, freq="h")
        candles = pd.DataFrame({
            "timestamps": timestamps,
            "open": [base - 1.0, base],
            "high": [base, base + 1.0],
            "low": [base - 2.0, base - 1.0],
            "close": [base - 1.0, base],
            "volume": [10.0, 11.0],
            "amount": [(base - 1.0) * 10.0, base * 11.0],
        })
        future = pd.Series(pd.date_range("2026-01-01T02:00:00", periods=2, freq="h"))
        return {
            "df": candles,
            "x_timestamp": candles["timestamps"],
            "y_timestamp": future,
            "pred_len": 2,
        }


class FakeModelRunner:
    def __init__(self):
        self.configured = []
        self.predicted = []
        self.current = None

    def configure(self, model_name, device, model_id=None):
        self.configured.append((model_name, device))
        self.current = model_name
        return self

    def _forecast(self, df, y_timestamp):
        closing_price = float(df["close"].iloc[-1])
        offset = {"kronos-mini": 1.0, "kronos-small": 2.0, "kronos-base": -1.0}[self.current]
        close = closing_price + offset
        return pd.DataFrame({
            "open": [close] * 2,
            "high": [close] * 2,
            "low": [close] * 2,
            "close": [close] * 2,
            "volume": [12.0] * 2,
            "amount": [close * 12.0] * 2,
        }, index=pd.DatetimeIndex(y_timestamp))

    def predict(self, df, y_timestamp, **kwargs):
        self.predicted.append(self.current)
        return self._forecast(df, y_timestamp)

    def predict_batch(self, df_list, y_timestamp_list, **kwargs):
        self.predicted.append(self.current)
        return [self._forecast(df, ts) for df, ts in zip(df_list, y_timestamp_list)]


def test_single_service_runs_every_model_and_preserves_primary_chart():
    runner = FakeModelRunner()
    service = PricePredictionService(data_service=FakeOHLCVSource(), prediction_service=runner)
    request = PricePredictionRequest(symbol="ETHUSDT", model_name="kronos-small", lookback=2, pred_len=2)

    result = service.predict_price(request)
    parsed = PricePredictionResponse.model_validate(result)

    assert runner.predicted == list(DEFAULT_MODELS)
    assert parsed.request.model_name == "kronos-small"
    assert parsed.prediction[-1].close == 102.0
    assert len(parsed.model_comparisons) == 3
    assert {item.model_name for item in parsed.model_comparisons} == set(DEFAULT_MODELS)
    assert {item.model_name: item.direction for item in parsed.model_comparisons} == {
        "kronos-mini": "up", "kronos-small": "up", "kronos-base": "down"
    }


def test_batch_service_runs_every_model_for_every_symbol():
    runner = FakeModelRunner()
    service = BatchPricePredictionService(data_service=FakeOHLCVSource(), prediction_service=runner)
    requests = [
        PricePredictionRequest(symbol="ETHUSDT", model_name="kronos-base", lookback=2, pred_len=2),
        PricePredictionRequest(symbol="BTCUSDT", model_name="kronos-base", lookback=2, pred_len=2),
    ]

    results = service.predict_batch(requests)
    parsed = [PricePredictionResponse.model_validate(result) for result in results]

    assert runner.predicted == list(DEFAULT_MODELS)
    assert len(parsed) == 2
    assert [x.request.symbol for x in parsed] == ["ETHUSDT", "BTCUSDT"]
    assert [x.prediction[-1].close for x in parsed] == [99.0, 199.0]
    assert all(len(x.model_comparisons) == 3 for x in parsed)
    assert all({i.model_name for i in x.model_comparisons} == set(DEFAULT_MODELS) for x in parsed)
