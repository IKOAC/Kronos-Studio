from typing import List

import pandas as pd

from constants.available_models import AVAILABLE_MODELS
from errors.errors import (ModelLoadError, PredictionAPIError,
                           PredictionRuntimeError,
                           UnsupportedPredictionOptionError)
from schemas.prediction import (PredictionOptionsResponse,
                                PricePredictionRequest)
from services.prediction_service.prediction import KronosPredictionService
from services.raw_data_service.ohlcv_data import OHLCVDataService


class BatchPricePredictionService:
    """API-facing service for batch predictions on multiple time series."""

    def __init__(
        self,
        data_service: OHLCVDataService | None = None,
        prediction_service: KronosPredictionService | None = None,
    ):
        """Create the service with default or injected data/prediction services."""
        self.data_service = data_service or OHLCVDataService()
        self.prediction_service = prediction_service or KronosPredictionService()

    def predict_batch(
        self,
        requests: List[PricePredictionRequest],
    ) -> list[PredictionOptionsResponse]:
        """
        Fetch data for multiple requests and run batch predictions.

        All requests must have:
        - Same model_name
        - Same device
        - Same lookback period
        - Same pred_len

        Args:
            requests: List of PricePredictionRequest objects

        Returns:
            Dictionary with batch results:
          [
                    {
                        "request": PricePredictionRequest,
                        "data_source": str,
                        "symbol": str,
                        "lookback_start_timestamp": str,
                        "lookback_end_timestamp": str,
                        "prediction_start_timestamp": str,
                        "history": List[dict],
                        "future_timestamps": List[str],
                        "prediction": List[dict],
                    },
                    ...
                ]
        """
        if not requests:
            raise ValueError("At least one request is required for batch prediction.")

        # Validate all requests have compatible settings
        self._validate_batch_requests(requests)

        # Get first request for batch config
        first_request = requests[0]
        lookback = first_request.lookback
        pred_len = first_request.pred_len

        # Configure the prediction service
        self.prediction_service.configure(
            model_name=first_request.model_name,
            device=first_request.device,
        )

        # Load data for all requests
        prepared_data_list = []
        for request in requests:
            try:
                prepared_data = self._load_data(request)
                prepared_data_list.append(prepared_data)
            except Exception as exc:
                raise PredictionRuntimeError(
                    f"Failed to load data for {request.data_source}",
                    details={
                        "data_source": request.data_source,
                        "symbol": request.symbol or request.local_path,
                    },
                ) from exc

        # Extract lists for batch prediction
        df_list = [pd["df"] for pd in prepared_data_list]
        x_timestamp_list = [pd["x_timestamp"] for pd in prepared_data_list]
        y_timestamp_list = [pd["y_timestamp"] for pd in prepared_data_list]

        # Run the whole batch once per available model.
        model_predictions = {}
        active_model_name = first_request.model_name
        try:
            for active_model_name in AVAILABLE_MODELS:
                self.prediction_service.configure(
                    model_name=active_model_name,
                    device=first_request.device,
                )
                model_predictions[active_model_name] = self.prediction_service.predict_batch(
                    df_list=df_list,
                    x_timestamp_list=x_timestamp_list,
                    y_timestamp_list=y_timestamp_list,
                    pred_len=pred_len,
                    temperature=first_request.temperature,
                    top_k=first_request.top_k,
                    top_p=first_request.top_p,
                    sample_count=first_request.sample_count,
                    verbose=first_request.verbose,
                )
        except PredictionAPIError:
            raise
        except (OSError, FileNotFoundError) as exc:
            raise ModelLoadError(
                f"Could not load Kronos model '{active_model_name}'.",
                details={"model_name": active_model_name, "device": first_request.device},
            ) from exc
        except RuntimeError as exc:
            raise PredictionRuntimeError(
                f"Batch prediction failed while running model '{active_model_name}'.",
                details={
                    "model_name": active_model_name,
                    "device": first_request.device,
                    "reason": str(exc),
                },
            ) from exc
        except Exception as exc:
            raise PredictionRuntimeError(
                f"Batch prediction failed unexpectedly for model '{active_model_name}'.",
                details={"model_name": active_model_name},
            ) from exc

        # Format one comparison result per input series.
        results = []
        for i, (request, prepared_data) in enumerate(zip(requests, prepared_data_list)):
            prediction_df = model_predictions[request.model_name][i].reset_index(names="timestamps")
            per_item_predictions = {
                model_name: forecasts[i] for model_name, forecasts in model_predictions.items()
            }
            model_comparisons = self._build_model_comparisons(
                model_predictions=per_item_predictions,
                last_history_close=float(prepared_data["df"]["close"].iloc[-1]),
                sample_count=request.sample_count,
            )

            result = {
                "request": request.model_dump(),
                "model": AVAILABLE_MODELS[request.model_name],
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

            results.append(result)
            results.append(result)
        return results

        # return {
        #     "request_count": len(requests),
        #     "model": AVAILABLE_MODELS[first_request.model_name],
        #     "lookback": lookback,
        #     "pred_len": pred_len,
        #     "results": results,
        # }

    def _build_model_comparisons(
        self,
        model_predictions: dict,
        last_history_close: float,
        sample_count: int,
    ) -> list[dict]:
        """Summarize forecasts and directional consensus, not probability of accuracy."""
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
            if score >= 99.9:
                label = "High agreement"
            elif score >= 50.0:
                label = "Moderate agreement"
            else:
                label = "Low agreement"
            serializable_df = forecast_df.reset_index(names="timestamps")
            comparisons.append({
                "model_name": model_name,
                "model": AVAILABLE_MODELS[model_name],
                "prediction": self._records_to_json(serializable_df),
                "direction": direction,
                "predicted_change_pct": round(changes[model_name], 4),
                "confidence_score": round(score, 1),
                "confidence_label": label,
                "sample_count": sample_count,
                "direction_counts": direction_counts,
            })
        return comparisons

    def _validate_batch_requests(self, requests: List[PricePredictionRequest]):
        """Ensure all requests are compatible for batch processing."""
        if not requests:
            return

        first = requests[0]

        for i, request in enumerate(requests[1:], start=1):
            if request.model_name != first.model_name:
                raise UnsupportedPredictionOptionError(
                    f"Request {i}: model_name mismatch. All requests must use same model.",
                    details={
                        "request_0_model": first.model_name,
                        f"request_{i}_model": request.model_name,
                    },
                )

            if request.device != first.device:
                raise UnsupportedPredictionOptionError(
                    f"Request {i}: device mismatch. All requests must use same device.",
                    details={
                        "request_0_device": first.device,
                        f"request_{i}_device": request.device,
                    },
                )

            if request.lookback != first.lookback:
                raise UnsupportedPredictionOptionError(
                    f"Request {i}: lookback mismatch. All requests must have same lookback.",
                    details={
                        "request_0_lookback": first.lookback,
                        f"request_{i}_lookback": request.lookback,
                    },
                )

            if request.pred_len != first.pred_len:
                raise UnsupportedPredictionOptionError(
                    f"Request {i}: pred_len mismatch. All requests must have same pred_len.",
                    details={
                        "request_0_pred_len": first.pred_len,
                        f"request_{i}_pred_len": request.pred_len,
                    },
                )

    def _load_data(self, request: PricePredictionRequest):
        """Load OHLCV data from the selected source."""
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
        if hasattr(timestamp, "isoformat"):
            ts = timestamp
            if ts.tz is not None:
                ts = ts.tz_localize(None)
            return ts.isoformat()
        return str(timestamp)
