import pandas as pd

from constants.available_models import AVAILABLE_MODELS, model_metadata
from services.prediction_service.adapters import validate_selection
from errors.errors import (ModelLoadError, PredictionAPIError,
                           PredictionRuntimeError,
                           UnsupportedPredictionOptionError)
from schemas.prediction import PricePredictionRequest
from services.prediction_service.prediction import KronosPredictionService
from services.raw_data_service.ohlcv_data import OHLCVDataService


class PricePredictionService:
    """API-facing service that fetches candles and runs Kronos predictions."""

    def __init__(
        self,
        data_service: OHLCVDataService | None = None,
        prediction_service: KronosPredictionService | None = None,
    ):
        """Create the service with default or injected data/prediction services."""
        self.data_service = data_service or OHLCVDataService()
        self.prediction_service = prediction_service or KronosPredictionService()

    def predict_price(self, request: PricePredictionRequest):
        """Fetch selected data, run the selected model, and return JSON-safe output."""
        validate_selection(request)
        prepared_data = self._load_data(request)

        # Run only selected models; model_name controls the primary chart.
        model_predictions = {}
        active_model_name = request.model_name
        try:
            for active_model_name in request.selected_models:
                self.prediction_service.configure(
                    model_name=active_model_name,
                    device=request.device,
                    model_id=request.model_ids.get(active_model_name),
                )
                model_predictions[active_model_name] = self.prediction_service.predict(
                    df=prepared_data["df"],
                    x_timestamp=prepared_data["x_timestamp"],
                    y_timestamp=prepared_data["y_timestamp"],
                    pred_len=prepared_data["pred_len"],
                    temperature=request.temperature,
                    top_k=request.top_k,
                    top_p=request.top_p,
                    sample_count=request.sample_count,
                    verbose=request.verbose,
                )
        except PredictionAPIError:
            raise
        except (OSError, FileNotFoundError) as exc:
            raise ModelLoadError(
                f"Could not load model '{active_model_name}'. Check model files or network access.",
                details={"model_name": active_model_name, "device": request.device},
            ) from exc
        except RuntimeError as exc:
            raise PredictionRuntimeError(
                f"Prediction failed while running model '{active_model_name}'.",
                details={
                    "model_name": active_model_name,
                    "device": request.device,
                    "reason": str(exc),
                },
            ) from exc
        except Exception as exc:
            raise PredictionRuntimeError(
                f"Prediction failed unexpectedly for model '{active_model_name}'.",
                details={"model_name": active_model_name, "device": request.device},
            ) from exc

        prediction_df = model_predictions[request.model_name]
        model_comparisons = self._build_model_comparisons(
            model_predictions=model_predictions,
            last_history_close=float(prepared_data["df"]["close"].iloc[-1]),
            sample_count=request.sample_count,
            model_ids=request.model_ids,
        )

        # Move prediction timestamps from the DataFrame index into the API response.
        prediction_df = prediction_df.reset_index(names="timestamps")

        return {
            "request": request.model_dump(),
            "model": model_metadata(request.model_name, request.model_ids),
            "lookback_start_timestamp": self._timestamp_to_json(
                prepared_data["x_timestamp"].iloc[0]
            ),
            "lookback_end_timestamp": self._timestamp_to_json(
                prepared_data["x_timestamp"].iloc[-1]
            ),
            "prediction_start_timestamp": self._timestamp_to_json(
                prepared_data["y_timestamp"].iloc[0]
            ),
            "history": self._records_to_json(prepared_data["df"]),
            "future_timestamps": self._timestamps_to_json(prepared_data["y_timestamp"]),
            "prediction": self._records_to_json(prediction_df),
            "model_comparisons": model_comparisons,
        }

    def _build_model_comparisons(
        self,
        model_predictions: dict,
        last_history_close: float,
        sample_count: int,
        model_ids: dict | None = None,
    ) -> list[dict]:
        """Summarize forecasts and directional consensus; this is not accuracy probability."""
        directions = {}
        changes = {}
        baseline = float(last_history_close)

        for model_name, forecast_df in model_predictions.items():
            final_close = float(forecast_df["close"].iloc[-1])
            change_pct = ((final_close - baseline) / abs(baseline) * 100.0) if baseline != 0 else 0.0
            if change_pct > 0.1:
                direction = "up"
            elif change_pct < -0.1:
                direction = "down"
            else:
                direction = "flat"
            directions[model_name] = direction
            changes[model_name] = change_pct

        direction_counts = {
            direction: sum(1 for value in directions.values() if value == direction)
            for direction in ("up", "down", "flat")
        }
        model_count = max(len(model_predictions), 1)
        comparisons = []
        for model_name, forecast_df in model_predictions.items():
            direction = directions[model_name]
            score = direction_counts[direction] / model_count * 100.0
            if model_count < 2:
                score = 0.0
                label = "Not comparable"
            elif score >= 99.9:
                label = "High agreement"
            elif score >= 50.0:
                label = "Moderate agreement"
            else:
                label = "Low agreement"
            serializable_df = forecast_df.reset_index(names="timestamps")
            comparisons.append({
                "model_name": model_name,
                "model": model_metadata(model_name, model_ids),
                "prediction": self._records_to_json(serializable_df),
                "direction": direction,
                "predicted_change_pct": round(changes[model_name], 4),
                "confidence_score": round(score, 1),
                "confidence_label": label,
                "sample_count": sample_count if AVAILABLE_MODELS[model_name]["adapter"] == "kronos" else 1,
                "direction_counts": direction_counts,
            })
        return comparisons

    def get_options(self):
        """Return values a client can show as selectable prediction options."""
        return {
            "data_sources": ["binance", "yfinance", "local"],
            "models": AVAILABLE_MODELS,
            "devices": ["cpu", "cuda:0", "mps"],
            "common_intervals": ["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
            "common_periods": ["5d", "1mo", "3mo", "6mo", "1y", "2y"],
            "defaults": PricePredictionRequest().model_dump(),
        }

    def _load_data(self, request: PricePredictionRequest):
        """Load OHLCV data from the selected source and prepare it for prediction."""
        if request.model_name not in AVAILABLE_MODELS:
            available = ", ".join(AVAILABLE_MODELS.keys())
            raise UnsupportedPredictionOptionError(
                f"Unknown model '{request.model_name}'. Available models: {available}",
                details={
                    "field": "model_name",
                    "received": request.model_name,
                    "available": list(AVAILABLE_MODELS.keys()),
                },
            )

        if request.data_source == "binance":
            if not request.symbol:
                raise UnsupportedPredictionOptionError(
                    "symbol is required for Binance data.",
                    details={"field": "symbol", "data_source": "binance"},
                )
            return self.data_service.get_data_from_binance(
                symbol=request.symbol,
                interval=request.interval,
                lookback=request.lookback,
                pred_len=request.pred_len,
                limit=request.limit,
            )

        if request.data_source == "yfinance":
            if not request.symbol:
                raise UnsupportedPredictionOptionError(
                    "symbol is required for Yahoo Finance data.",
                    details={"field": "symbol", "data_source": "yfinance"},
                )
            return self.data_service.get_data_from_yfinance(
                symbol=request.symbol,
                period=request.period,
                interval=request.interval,
                lookback=request.lookback,
                pred_len=request.pred_len,
            )

        if not request.local_path:
            raise UnsupportedPredictionOptionError(
                "local_path is required for local data.",
                details={"field": "local_path", "data_source": "local"},
            )
        return self.data_service.get_data_from_local_storage(
            path=request.local_path,
            lookback=request.lookback,
            pred_len=request.pred_len,
        )

    def _records_to_json(self, df: pd.DataFrame):
        """Convert a DataFrame into JSON-safe row dictionaries."""
        result = df.copy()
        for column in result.columns:
            if pd.api.types.is_datetime64_any_dtype(result[column]):
                result[column] = result[column].dt.strftime("%Y-%m-%dT%H:%M:%S")
        return result.to_dict(orient="records")

    def _timestamps_to_json(self, timestamps):
        """Convert timestamp values into ISO strings for JSON responses."""
        return [self._timestamp_to_json(timestamp) for timestamp in timestamps]

    def _timestamp_to_json(self, timestamp):
        """Convert one timestamp value into an ISO string for JSON responses."""
        if hasattr(timestamp, "strftime"):
            return timestamp.strftime("%Y-%m-%dT%H:%M:%S")
        return str(timestamp)
