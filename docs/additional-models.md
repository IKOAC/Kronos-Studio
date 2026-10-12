# Additional forecast models

Open **Choose models** in Run setup. Check the models you want to run and choose
one of the checked models as the primary chart. Single and Batch retain separate
selections. The original three Kronos models are selected by default.

| Model | Default Hugging Face ID | Output | Maximum history / forecast steps |
| --- | --- | --- | --- |
| Kronos Mini | `NeoQuasar/Kronos-mini` | Candles | 2048 / 2048 |
| Kronos Small | `NeoQuasar/Kronos-small` | Candles | 512 / 512 |
| Kronos Base | `NeoQuasar/Kronos-base` | Candles | 512 / 512 |
| Chronos-2 | `amazon/chronos-2` | Closing price | 8192 / 1024 |
| TimesFM 2.5 | `google/timesfm-2.5-200m-pytorch` | Closing price | 16384 / 1024 |
| FinCast v1 | `Vincent05R/FinCast` | Closing price | 1024 / 256 |

These are the limits supported by the app's adapters. All selected models use the
same history and forecast horizon. Requests exceeding any selected model's limit
are rejected before inference.

## Install and run

From the repository root, install the optional adapters and start the backend:

```sh
cd server
uv sync --extra forecast-models --extra fincast --inexact
./.venv/bin/python start_server.py
```

In a second terminal:

```sh
cd ~/Kronos-Studio/frontend
npm run dev
```

Alternatively run `uv run --extra forecast-models --extra fincast python start_server.py`.
Keep both extras on subsequent `uv sync` or `uv run` commands; running without
extras can remove their dependencies. `--inexact` preserves other installed packages.
New model weights download from Hugging Face only when selected for prediction.
FinCast's first download is approximately 4 GB.

Kronos supports CPU, CUDA and MPS. The new adapters currently support CPU and CUDA.
Selecting a new adapter while using MPS changes the device to CPU; the device
picker shows the choices supported by the current selection. CPU inference,
especially FinCast, can take substantially longer than Kronos Mini.

## Custom checkpoints

Each checked model exposes a **Hugging Face ID** field. Replace the official ID
with an `owner/model` ID for a checkpoint compatible with that adapter. **Reset ID**
restores the official checkpoint. The comparison and saved response record the
ID actually used. These fields do not load arbitrary Hugging Face architectures.

- Kronos checkpoints must use the same architecture and original tokenizer as the
  chosen variant. The tokenizer IDs stay paired with Mini, Small and Base.
- Chronos-2 checkpoints must work with `Chronos2Pipeline`.
- TimesFM checkpoints must match the native TimesFM 2.5 200M PyTorch format.
- FinCast checkpoints must match the public v1 architecture and contain `v1.pth`.
  Its inference code is pinned to upstream commit `488b19d1d85fa2b3d4b93469530cefdcf1cc97a4`.

## Forecast semantics

Chronos-2 uses historical open, high, low and volume as past covariates for close.
TimesFM and FinCast forecast the closing-price series. All forecasts use the
same future timestamps supplied by the data source. New adapters return null for
unpredicted open, high, low, volume and amount. Their primary chart uses Line mode;
live Binance overlays still show actual candles behind every selected forecast.
CSV exports leave unpredicted values blank.

Kronos sampling settings apply only to Kronos. Other adapters return a point
forecast and report a sample count of one. Directional agreement is calculated
over the selected models; a single model is marked **Not comparable**. Agreement
is not a calibrated probability of correctness.

## API additions

`selected_models` chooses the model keys to run. `model_name` must be included in
that list and controls the primary chart. `model_ids` optionally overrides IDs
for selected keys. All batch items must share these fields.

```json
{
  "model_name": "chronos-2",
  "selected_models": ["kronos-mini", "chronos-2"],
  "model_ids": {"chronos-2": "amazon/chronos-2"},
  "device": "cpu"
}
```

Older requests without `selected_models` continue to run the original three
Kronos models. A new primary model without a selection runs that model alone.
