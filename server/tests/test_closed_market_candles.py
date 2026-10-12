"""Forecast input must exclude Binance's still-open candle."""

from urllib.parse import parse_qs, urlsplit
from types import SimpleNamespace
import pytest
from errors.errors import DataNotFoundError
from services.raw_data_service.ohlcv_data import OHLCVDataService


def row(open_time, close_time):
    return [
        open_time,
        "100",
        "101",
        "99",
        "100",
        "10",
        close_time,
        "1000",
        1,
        "1",
        "100",
        "0",
    ]


def test_closed_candles_keep_lookback_and_forecast_timestamps(monkeypatch):
    urls = []

    def get(url, **kwargs):
        urls.append(url)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [
                row(0, 3599999),
                row(3600000, 7199999),
                row(7200000, 9999999999999),
            ],
        )

    monkeypatch.setattr("services.raw_data_service.ohlcv_data.requests.get", get)
    result = OHLCVDataService().get_data_from_binance(
        "ETHUSDT", lookback=2, limit=2, pred_len=2
    )
    assert len(result["df"]) == 2
    assert str(result["x_timestamp"].iloc[-1]) == "1970-01-01 01:00:00"
    assert str(result["y_timestamp"].iloc[0]) == "1970-01-01 02:00:00"
    assert parse_qs(urlsplit(urls[0]).query)["limit"] == ["3"]


def test_no_completed_candles_reports_data_unavailable(monkeypatch):
    monkeypatch.setattr(
        "services.raw_data_service.ohlcv_data.requests.get",
        lambda *a, **k: SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: [row(0, 9999999999999)]
        ),
    )
    with pytest.raises(DataNotFoundError, match="completed"):
        OHLCVDataService().get_data_from_binance("ETHUSDT", lookback=2)
