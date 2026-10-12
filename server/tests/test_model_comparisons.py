import pandas as pd
import pytest

from services.prediction_service.batch_price_prediction import BatchPricePredictionService
from services.prediction_service.price_prediction import PricePredictionService


def forecast(final_close: float) -> pd.DataFrame:
    """Build a minimal forecast DataFrame with the columns used by comparison scoring."""
    return pd.DataFrame(
        {
            "open": [final_close],
            "high": [final_close],
            "low": [final_close],
            "close": [final_close],
            "volume": [10.0],
            "amount": [10.0 * final_close],
        },
        index=pd.DatetimeIndex(["2026-01-01T00:00:00"]),
    )


@pytest.mark.parametrize(
    "service_type",
    [PricePredictionService, BatchPricePredictionService],
)
def test_model_comparison_scores_directional_agreement(service_type):
    service = object.__new__(service_type)
    predictions = {
        "kronos-mini": forecast(102.0),
        "kronos-small": forecast(101.0),
        "kronos-base": forecast(99.0),
    }

    comparisons = service._build_model_comparisons(
        model_predictions=predictions,
        last_history_close=100.0,
        sample_count=1,
    )
    by_model = {item["model_name"]: item for item in comparisons}

    assert by_model["kronos-mini"]["direction"] == "up"
    assert by_model["kronos-mini"]["confidence_score"] == 66.7
    assert by_model["kronos-mini"]["confidence_label"] == "Moderate agreement"
    assert by_model["kronos-small"]["confidence_score"] == 66.7
    assert by_model["kronos-base"]["direction"] == "down"
    assert by_model["kronos-base"]["confidence_score"] == 33.3
    assert by_model["kronos-base"]["confidence_label"] == "Low agreement"


@pytest.mark.parametrize(
    "service_type",
    [PricePredictionService, BatchPricePredictionService],
)
def test_unanimous_direction_is_high_agreement(service_type):
    service = object.__new__(service_type)
    predictions = {
        "kronos-mini": forecast(102.0),
        "kronos-small": forecast(101.0),
        "kronos-base": forecast(100.5),
    }

    comparisons = service._build_model_comparisons(
        model_predictions=predictions,
        last_history_close=100.0,
        sample_count=1,
    )

    assert len(comparisons) == 3
    assert all(item["confidence_score"] == 100.0 for item in comparisons)
    assert all(item["confidence_label"] == "High agreement" for item in comparisons)
