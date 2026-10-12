"""Quota checkpoints must never erase locally recorded request attempts."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def monitor(tmp_path):
    source = Path(__file__).resolve().parents[2] / "scripts" / "groq_usage_monitor.py"
    spec = importlib.util.spec_from_file_location("test_usage_monitor", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HOME = tmp_path
    module.LOG = tmp_path / "usage.jsonl"
    module.STATE = tmp_path / "alert_state.json"
    return module


def record(monitor, status=200, remaining=None):
    headers = {} if remaining is None else {
        "x-ratelimit-limit-requests": "1000",
        "x-ratelimit-remaining-requests": str(remaining),
    }
    monitor.record(monitor.MODEL, {"prompt_tokens": 100}, headers, status)


def test_repeated_provider_checkpoint_does_not_erase_local_requests(monitor):
    record(monitor, remaining=999)
    record(monitor, remaining=999)
    assert monitor.report()["requests_used"] == 2


def test_provider_checkpoint_includes_other_account_calls(monitor):
    record(monitor, remaining=900)
    record(monitor, status=0)
    assert monitor.report()["requests_used"] == 101


def test_failed_attempt_without_headers_is_counted(monitor):
    record(monitor, status=502)
    assert monitor.report()["requests_used"] == 1


def test_pending_alerts_and_token_total_survive_request_correction(monitor):
    monitor.record(monitor.MODEL, {"prompt_tokens": 11000}, {}, 200)
    before = monitor.report()
    record(monitor, remaining=999)
    after = monitor.report()
    assert before["pending_5pct_alerts"] == after["pending_5pct_alerts"] == [5]
    assert after["tokens_observed"] == 11100
    assert not monitor.STATE.exists()
