from typing import Literal

from pydantic import BaseModel, Field, model_validator
from huggingface_hub.utils import validate_repo_id

from constants.available_models import DEFAULT_MODELS

DataSource = Literal["binance", "yfinance", "local"]
ModelName = Literal["kronos-mini", "kronos-small", "kronos-base", "chronos-2", "timesfm-2.5", "fincast"]
Device = Literal["cpu", "cuda:0", "mps"]


class PricePredictionRequest(BaseModel):
    """User-selectable inputs for price prediction."""

    data_source: DataSource = Field(default="binance")
    symbol: str | None = Field(
        default="ETHUSDT", examples=["BTCUSDT", "BTC-USDT", "AAPL"]
    )
    local_path: str | None = None
    period: str = "30d"
    interval: str = "1h"
    lookback: int = Field(default=400, ge=2)
    pred_len: int = Field(default=120, ge=1)
    limit: int | None = Field(default=400, ge=1)
    model_name: ModelName = "kronos-mini"
    selected_models: list[ModelName] | None = Field(default=None, min_length=1, max_length=6)
    model_ids: dict[ModelName, str] = Field(default_factory=dict)
    device: Device = "cpu"
    temperature: float = Field(default=1.0, gt=0)
    top_k: int = Field(default=0, ge=0)
    top_p: float = Field(default=0.9, gt=0, le=1)
    sample_count: int = Field(default=1, ge=1)
    verbose: bool = False

    @model_validator(mode="after")
    def validate_models(self):
        # Older clients omit selection and keep the original three-model behavior.
        if self.selected_models is None:
            self.selected_models = list(DEFAULT_MODELS) if self.model_name in DEFAULT_MODELS else [self.model_name]
        if len(set(self.selected_models)) != len(self.selected_models):
            raise ValueError("Choose each model only once.")
        if self.model_name not in self.selected_models:
            raise ValueError("The primary chart model must be included in selected_models.")
        for key, value in self.model_ids.items():
            if key not in self.selected_models:
                raise ValueError("Hugging Face overrides must belong to selected models.")
            validate_repo_id(value)
            if "/" not in value:
                raise ValueError("Use a Hugging Face ID in the form owner/model.")
        return self


class AvailableModel(BaseModel):
    """Metadata for one selectable Kronos model."""

    name: str
    model_id: str
    tokenizer_id: str | None = None
    context_length: int
    params: str
    description: str
    adapter: str = "kronos"
    output_type: Literal["candles", "close"] = "candles"
    devices: list[Device] = Field(default_factory=lambda: ["cpu", "cuda:0", "mps"])
    max_horizon: int | None = None


class CandleRecord(BaseModel):
    """One OHLCV row returned by the prediction API."""

    timestamps: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


class PredictionOptionsResponse(BaseModel):
    """Selectable values and defaults for prediction requests."""

    data_sources: list[DataSource]
    models: dict[ModelName, AvailableModel]
    devices: list[Device]
    common_intervals: list[str]
    common_periods: list[str]
    defaults: PricePredictionRequest


class ForecastRecord(BaseModel):
    """Forecasts may contain only a closing price; missing candles are not synthesized."""

    timestamps: str
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    amount: float | None = None


class UploadedDataFileResponse(BaseModel):
    """Metadata for a CSV uploaded for local predictions."""

    filename: str
    stored_path: str
    size_bytes: int
    row_count: int
    columns: list[str]


class ModelComparison(BaseModel):
    """One model's forecast and cross-model directional agreement."""

    model_name: ModelName
    model: AvailableModel
    prediction: list[ForecastRecord]
    direction: Literal["up", "down", "flat"]
    predicted_change_pct: float
    confidence_score: float = Field(ge=0, le=100)
    confidence_label: Literal["Low agreement", "Moderate agreement", "High agreement", "Not comparable"]
    sample_count: int = Field(ge=1)
    direction_counts: dict[str, int]


class PricePredictionResponse(BaseModel):
    """Prediction output with source history and future candles."""

    request: PricePredictionRequest
    model: AvailableModel
    lookback_start_timestamp: str
    lookback_end_timestamp: str
    prediction_start_timestamp: str
    history: list[CandleRecord]
    future_timestamps: list[str]
    prediction: list[ForecastRecord]
    model_comparisons: list[ModelComparison] = Field(default_factory=list)
