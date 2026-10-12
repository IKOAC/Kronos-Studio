"""Adapters for public, architecture-compatible time-series checkpoints.

The three adapters predict closing prices. Missing OHLCV fields remain null.
Imports are lazy so the original Kronos app also works without these extras.
"""

import math

import numpy as np
import pandas as pd
import torch

from constants.available_models import AVAILABLE_MODELS
from errors.errors import ModelLoadError, PredictionRuntimeError, UnsupportedPredictionOptionError


def validate_selection(request):
    for name in request.selected_models:
        config = AVAILABLE_MODELS[name]
        if request.device not in config["devices"]:
            raise UnsupportedPredictionOptionError(
                f"{config['name']} supports CPU and CUDA. Choose CPU on this Mac.",
                details={"model_name": name, "device": request.device},
            )
        if request.lookback > config["context_length"]:
            raise UnsupportedPredictionOptionError(
                f"{config['name']} supports up to {config['context_length']} history points. Reduce Lookback.",
                details={"model_name": name, "field": "lookback"},
            )
        maximum = config.get("max_horizon", config["context_length"])
        if request.pred_len > maximum:
            raise UnsupportedPredictionOptionError(
                f"{config['name']} supports up to {maximum} forecast steps. Reduce Predict Length.",
                details={"model_name": name, "field": "pred_len"},
            )
    if request.device.startswith("cuda") and not torch.cuda.is_available():
        raise UnsupportedPredictionOptionError("CUDA is unavailable. Choose CPU or a supported device.")
    if request.device == "mps" and not torch.backends.mps.is_available():
        raise UnsupportedPredictionOptionError("MPS is unavailable. Choose CPU.")


def close_frame(values, timestamps, pred_len):
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    if len(values) != pred_len or len(timestamps) != pred_len or not np.isfinite(values).all():
        raise PredictionRuntimeError("The model returned an invalid or incomplete closing-price forecast.")
    return pd.DataFrame(
        {"close": values, "open": None, "high": None, "low": None, "volume": None, "amount": None},
        index=pd.DatetimeIndex(timestamps),
    )


class ClosePriceAdapter:
    def predict(self, df, y_timestamp, pred_len, **kwargs):
        values = self.forecast(df, pred_len, kwargs.get("x_timestamp"))
        return close_frame(values, y_timestamp, pred_len)

    def predict_batch(self, df_list, x_timestamp_list, y_timestamp_list, pred_len, **kwargs):
        # Load once, then process series individually to bound memory on local devices.
        return [self.predict(df, dates, pred_len, x_timestamp=history, **kwargs)
                for df, history, dates in zip(df_list, x_timestamp_list, y_timestamp_list, strict=True)]


class Chronos2Adapter(ClosePriceAdapter):
    def __init__(self, model_id, device):
        from chronos import Chronos2Pipeline

        self.pipeline = Chronos2Pipeline.from_pretrained(model_id, device_map=device, torch_dtype=torch.float32)

    def forecast(self, df, pred_len, timestamps):
        inputs = [{
            "target": df["close"].to_numpy(dtype=np.float32),
            "past_covariates": {col: df[col].to_numpy(dtype=np.float32)
                                for col in ("open", "high", "low", "volume")},
        }]
        with torch.inference_mode():
            _, means = self.pipeline.predict_quantiles(inputs, prediction_length=pred_len, batch_size=8)
        return means[0].detach().cpu().numpy().reshape(-1)


class TimesFM25Adapter(ClosePriceAdapter):
    def __init__(self, model_id, device):
        import timesfm

        self.timesfm = timesfm
        self.model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(model_id, torch_compile=False)
        self.model.model.to(device)
        self.model.model.device = torch.device(device)
        self.model.model.device_count = 1
        self.model.model.eval()
        self.shape = None

    def forecast(self, df, pred_len, timestamps):
        shape = (math.ceil(len(df) / 32) * 32, math.ceil(pred_len / 128) * 128)
        if shape != self.shape:
            self.model.compile(self.timesfm.ForecastConfig(
                max_context=shape[0], max_horizon=shape[1], per_core_batch_size=1,
                normalize_inputs=True, use_continuous_quantile_head=True, fix_quantile_crossing=True,
            ))
            self.shape = shape
        with torch.inference_mode():
            points, _ = self.model.forecast(horizon=pred_len, inputs=[df["close"].to_numpy(dtype=np.float32)])
        return points[0]


class FinCastAdapter(ClosePriceAdapter):
    def __init__(self, model_id, device):
        from ffm import FFM, FFmHparams
        from huggingface_hub import hf_hub_download

        self.model_class, self.hparams_class = FFM, FFmHparams
        self.checkpoint = hf_hub_download(repo_id=model_id, filename="v1.pth")
        self.device = device
        self.model = None
        self.shape = None

    def forecast(self, df, pred_len, timestamps):
        shape = (max(32, math.ceil(len(df) / 32) * 32), pred_len)
        if self.shape != shape:
            hparams = self.hparams_class(
                backend="gpu" if self.device.startswith("cuda") else "cpu",
                context_len=shape[0], horizon_len=pred_len, per_core_batch_size=1,
                num_experts=4, gating_top_n=2, load_from_compile=True,
                use_positional_embedding=False, point_forecast_mode="mean",
            )
            self.model = self.model_class(hparams=hparams, checkpoint=self.checkpoint, loading_mode=0)
            self.model.model_eval_mode()
            self.shape = shape
        step = pd.Timedelta(pd.to_datetime(timestamps.iloc[-1]) - pd.to_datetime(timestamps.iloc[-2]))
        frequency = 2 if step >= pd.Timedelta(days=90) else 1 if step >= pd.Timedelta(days=7) else 0
        with torch.inference_mode():
            points, _ = self.model.forecast([df["close"].to_numpy(dtype=np.float32)], freq=[frequency])
        return points[0, :pred_len]


def load_adapter(adapter, model_id, device):
    classes = {"chronos2": Chronos2Adapter, "timesfm25": TimesFM25Adapter, "fincast": FinCastAdapter}
    try:
        return classes[adapter](model_id, device)
    except ImportError as exc:
        extra = "fincast" if adapter == "fincast" else "forecast-models"
        raise ModelLoadError(
            f"Dependencies for {adapter} are missing. In the server folder run: uv sync --extra {extra}",
            details={"model_id": model_id, "reason": str(exc)},
        ) from exc
