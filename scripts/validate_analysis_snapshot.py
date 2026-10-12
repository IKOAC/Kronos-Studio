"""Validate actual saved forecast outputs against Python metrics; no Groq calls.

Usage: python scripts/validate_analysis_snapshot.py --single-file result.json
       --batch-file batch.json --output validation.json
The server must be running locally. Inputs should come from real model inference.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import urllib.request


def analysis_payload(result: dict) -> dict:
    comparisons = result.get("model_comparisons", [])
    forecasts = [
        {
            "model_name": item["model_name"],
            "final_close": item["prediction"][-1]["close"],
        }
        for item in comparisons
    ] or [
        {
            "model_name": result["request"]["model_name"],
            "final_close": result["prediction"][-1]["close"],
        }
    ]
    return {
        "symbol": result["request"]["symbol"],
        "interval": result["request"]["interval"],
        "history": [
            {
                key: row[key]
                for key in ("timestamps", "open", "high", "low", "close", "volume")
            }
            for row in result["history"]
        ],
        "forecasts": forecasts,
    }


def validate_result(result: dict) -> dict:
    body = analysis_payload(result)
    for item in result.get("model_comparisons", []):
        assert len(item["prediction"]) == result["request"]["pred_len"]
        assert [row["timestamps"] for row in item["prediction"]] == result[
            "future_timestamps"
        ]
        assert all(
            math.isfinite(row["close"]) and row["close"] > 0
            for row in item["prediction"]
        )
    closed = None
    if result["request"]["data_source"] == "binance":
        interval = re.fullmatch(r"(\d+)([smhdw])", body["interval"])
        if interval:
            seconds = (
                int(interval[1])
                * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[interval[2]]
            )
            ts = datetime.fromisoformat(body["history"][-1]["timestamps"])
            ts = (
                ts.replace(tzinfo=timezone.utc)
                if ts.tzinfo is None
                else ts.astimezone(timezone.utc)
            )
            closed = ts + timedelta(seconds=seconds) <= datetime.now(timezone.utc)
            assert closed, "Forecast history includes an incomplete candle"
    request = urllib.request.Request(
        "http://127.0.0.1:8000/api/analysis/metrics",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        metrics = json.load(response)
    assert metrics["technical"]["last_close"] == body["history"][-1]["close"]
    assert metrics["technical"]["candles"] == len(body["history"])
    assert len(metrics["forecast"]["models"]) == len(body["forecasts"])
    for calculated, forecast in zip(
        metrics["forecast"]["models"], body["forecasts"], strict=True
    ):
        assert calculated["model_name"] == forecast["model_name"]
        assert calculated["final_close"] == forecast["final_close"]
    for calculated, original in zip(
        metrics["forecast"]["models"], result.get("model_comparisons", [])
    ):
        assert calculated["direction"] == original["direction"]
        assert math.isclose(
            calculated["change_pct"], original["predicted_change_pct"], abs_tol=0.00006
        )
    return {
        "symbol": body["symbol"],
        "interval": body["interval"],
        "models": [item["model_name"] for item in body["forecasts"]],
        "history_candles": len(body["history"]),
        "forecast_steps": result["request"]["pred_len"],
        "closed_candles_checked": closed,
        "metrics_match_forecasts": True,
        "metrics_sha256": hashlib.sha256(
            json.dumps(metrics, sort_keys=True).encode()
        ).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--single-file", required=True, type=Path)
    parser.add_argument("--batch-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    single = json.loads(args.single_file.read_text())
    batch = json.loads(args.batch_file.read_text())
    assert isinstance(batch, list) and batch, "Expected a nonempty batch output"
    report = {
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "groq_calls": 0,
        "snapshots": [validate_result(item) for item in [single, *batch]],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
