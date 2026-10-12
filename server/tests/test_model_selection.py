"""Regression tests for selection, checkpoint routing and honest forecast output."""

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from constants.available_models import AVAILABLE_MODELS
from errors.errors import PredictionRuntimeError, UnsupportedPredictionOptionError
from schemas.prediction import PricePredictionRequest, PricePredictionResponse, PredictionOptionsResponse
from services.prediction_service.adapters import close_frame, validate_selection, ClosePriceAdapter
from services.prediction_service.price_prediction import PricePredictionService
from services.prediction_service.batch_price_prediction import BatchPricePredictionService


class DataSource:
    def get_data_from_binance(self, **kwargs):
        history = pd.Series(pd.date_range("2026-01-01", periods=4, freq="h"))
        future = pd.Series(pd.date_range(history.iloc[-1] + pd.Timedelta(hours=1), periods=2, freq="h"))
        df = pd.DataFrame({"timestamps": history, "open": [100.] * 4, "high": [101.] * 4,
                           "low": [99.] * 4, "close": [100.] * 4, "volume": [10.] * 4, "amount": [1000.] * 4})
        return dict(df=df, x_timestamp=history, y_timestamp=future, pred_len=2)


class Predictor:
    def __init__(self):
        self.calls = []

    def configure(self, model_name, device, model_id=None):
        self.name = model_name
        self.model_id = model_id

    def predict(self, df, x_timestamp, y_timestamp, pred_len, **kwargs):
        self.calls.append((self.name, self.model_id))
        price = 102. if self.name == "chronos-2" else 99.
        result = close_frame([price] * pred_len, y_timestamp, pred_len)
        if self.name.startswith("kronos-"):
            for column in ("open", "high", "low"):
                result[column] = price
            result["volume"] = 10.
            result["amount"] = price * 10.
        return result

    def predict_batch(self, df_list, x_timestamp_list, y_timestamp_list, pred_len, **kwargs):
        return [self.predict(df, x, y, pred_len, **kwargs)
                for df, x, y in zip(df_list, x_timestamp_list, y_timestamp_list)]


def request(**kwargs):
    return PricePredictionRequest(lookback=4, pred_len=2, **kwargs)


@pytest.mark.parametrize("batch", [False, True])
def test_only_selected_models_run_and_custom_checkpoint_survives_response(batch):
    predictor = Predictor()
    service_type = BatchPricePredictionService if batch else PricePredictionService
    service = service_type(DataSource(), predictor)
    req = request(model_name="chronos-2", selected_models=["kronos-mini", "chronos-2"],
                  model_ids={"chronos-2": "example/compatible-chronos"}, sample_count=5)
    results = service.predict_batch([req, req]) if batch else [service.predict_price(req)]
    assert {name for name, _ in predictor.calls} == {"kronos-mini", "chronos-2"}
    for raw in results:
        result = PricePredictionResponse.model_validate(raw)
        assert result.model.model_id == "example/compatible-chronos"
        assert result.model.output_type == "close"
        assert len(result.prediction) == 2
        assert result.prediction[0].open is None
        assert result.prediction[0].volume is None
        assert result.prediction[0].timestamps == "2026-01-01T04:00:00"
        assert [item.confidence_score for item in result.model_comparisons] == [50., 50.]
        assert [item.sample_count for item in result.model_comparisons] == [5, 1]
        assert result.model_comparisons[1].model.model_id == result.model.model_id


def test_single_model_is_not_reported_as_unanimous_agreement():
    result = PricePredictionService(DataSource(), Predictor()).predict_price(
        request(model_name="chronos-2", selected_models=["chronos-2"]))
    assert result["model_comparisons"][0]["confidence_label"] == "Not comparable"


@pytest.mark.parametrize("changes", [
    {"selected_models": []}, {"selected_models": ["kronos-mini", "kronos-mini"]},
    {"selected_models": ["chronos-2"]}, {"model_ids": {"kronos-mini": "../local-path"}},
    {"model_ids": {"fincast": "Vincent05R/FinCast"}},
])
def test_invalid_selection_or_checkpoint_rejected(changes):
    with pytest.raises(ValidationError):
        request(**changes)


def test_legacy_requests_keep_original_three_models():
    assert request().selected_models == ["kronos-mini", "kronos-small", "kronos-base"]
    assert request(model_name="fincast").selected_models == ["fincast"]


def test_batch_rejects_inconsistent_selection_and_checkpoint():
    service = BatchPricePredictionService(DataSource(), Predictor())
    for req in [request(selected_models=["kronos-mini"]),
                request(model_ids={"kronos-mini": "example/other"})]:
        with pytest.raises(UnsupportedPredictionOptionError):
            service.predict_batch([request(), req])


def test_device_and_horizon_limits_checked_before_model_load():
    with pytest.raises(UnsupportedPredictionOptionError, match="CPU"):
        validate_selection(request(model_name="fincast", device="mps"))
    with pytest.raises(UnsupportedPredictionOptionError, match="256"):
        validate_selection(PricePredictionRequest(model_name="fincast", pred_len=257))


@pytest.mark.parametrize("values", [[1.], [float("nan"), 2.], [1., float("inf")]])
def test_bad_forecast_cannot_reach_json(values):
    with pytest.raises(PredictionRuntimeError):
        close_frame(values, pd.date_range("2026-01-01", periods=2), 2)


def test_close_adapter_preserves_each_batch_timeline():
    class Adapter(ClosePriceAdapter):
        def forecast(self, df, pred_len, timestamps):
            return np.repeat(df["close"].iloc[-1], pred_len)
    dates = [pd.Series(pd.date_range(start, periods=2)) for start in ["2026-01-01", "2026-02-01"]]
    frames = Adapter().predict_batch([pd.DataFrame({"close": [1.]}), pd.DataFrame({"close": [2.]})], dates, dates, 2)
    assert frames[0].index[0] != frames[1].index[0]
    assert frames[1]["close"].tolist() == [2., 2.]
    assert frames[0]["volume"].isna().all()


def test_options_expose_all_checkpoint_ids():
    options = PredictionOptionsResponse.model_validate(PricePredictionService().get_options())
    assert set(options.models) == set(AVAILABLE_MODELS)
    assert options.models["chronos-2"].model_id == "amazon/chronos-2"
    assert options.models["fincast"].max_horizon == 256
