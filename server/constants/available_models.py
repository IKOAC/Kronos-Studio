# Available model configurations
AVAILABLE_MODELS = {
    "kronos-mini": {
        "name": "Kronos-mini",
        "model_id": "NeoQuasar/Kronos-mini",
        "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-2k",
        "context_length": 2048,
        "params": "4.1M",
        "description": "Lightweight model, suitable for fast prediction",
    },
    "kronos-small": {
        "name": "Kronos-small",
        "model_id": "NeoQuasar/Kronos-small",
        "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
        "context_length": 512,
        "params": "24.7M",
        "description": "Small model, balanced performance and speed",
    },
    "kronos-base": {
        "name": "Kronos-base",
        "model_id": "NeoQuasar/Kronos-base",
        "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
        "context_length": 512,
        "params": "102.3M",
        "description": "Base model, provides better prediction quality",
    },
}

for config in AVAILABLE_MODELS.values():
    config.update(adapter="kronos", output_type="candles", devices=["cpu", "cuda:0", "mps"])

AVAILABLE_MODELS.update({
    "chronos-2": {
        "name": "Chronos-2", "model_id": "amazon/chronos-2",
        "tokenizer_id": None, "context_length": 8192, "params": "120M",
        "description": "Closing-price forecast using historical candle and volume inputs.",
        "adapter": "chronos2", "output_type": "close", "devices": ["cpu", "cuda:0"],
        "max_horizon": 1024,
    },
    "timesfm-2.5": {
        "name": "TimesFM 2.5", "model_id": "google/timesfm-2.5-200m-pytorch",
        "tokenizer_id": None, "context_length": 16384, "params": "200M",
        "description": "General time-series model for closing-price forecasts.",
        "adapter": "timesfm25", "output_type": "close", "devices": ["cpu", "cuda:0"],
        "max_horizon": 1024,
    },
    "fincast": {
        "name": "FinCast", "model_id": "Vincent05R/FinCast",
        "tokenizer_id": None, "context_length": 1024, "params": "1B",
        "description": "Financial forecasting model. Downloads about 4 GB on first use.",
        "adapter": "fincast", "output_type": "close", "devices": ["cpu", "cuda:0"],
        "max_horizon": 256,
    },
})

DEFAULT_MODELS = ["kronos-mini", "kronos-small", "kronos-base"]


def model_metadata(model_name, model_ids=None):
    metadata = dict(AVAILABLE_MODELS[model_name])
    override = (model_ids or {}).get(model_name)
    if override and override != metadata["model_id"]:
        metadata.update(model_id=override, params="Custom checkpoint")
    return metadata
