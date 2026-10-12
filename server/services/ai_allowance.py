"""Read-only, cached account reporting. Keys and raw responses never leave this layer."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import ssl
import threading
import time
import urllib.error
import urllib.request

from schemas.ai_allowance import ProviderAllowance

CACHE_SECONDS = 60
ENDPOINTS = {
    "routeway": {"balance": "https://api.routeway.ai/v1/account/balance"},
    "openrouter": {
        "key": "https://openrouter.ai/api/v1/key",
        "balance": "https://openrouter.ai/api/v1/credits",
    },
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def send_allowance(url, key):
    # Callers cannot select an arbitrary host or send the management key to inference.
    if url not in {
        url for endpoints in ENDPOINTS.values() for url in endpoints.values()
    }:
        raise ValueError("Unsupported allowance endpoint")
    context = ssl.create_default_context(
        cafile="/etc/ssl/cert.pem" if Path("/etc/ssl/cert.pem").is_file() else None
    )
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context), NoRedirect()
    )
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + key,
            "User-Agent": "KronosStudioResearch/0.3",
        },
        method="GET",
    )
    try:
        with opener.open(request, timeout=5) as response:
            # Small read-only metadata; never persist the raw response or echo an error body.
            raw = response.read(65537)
            if len(raw) > 65536:
                return 0, {}
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        return 0, {}


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            if math.isfinite(value) and value >= 0:
                return float(value)
        except (OverflowError, ValueError):
            pass
    return None


class AllowanceReporter:
    def __init__(self, transport=None, clock=None):
        self.transport = transport or send_allowance
        self.clock = clock or time.monotonic
        self._cache = {}
        self._locks = {}
        self._guard = threading.Lock()

    @staticmethod
    def cache_key(provider, key, management_key):
        digest = hashlib.sha256(
            (key + "\0" + (management_key or "")).encode()
        ).hexdigest()
        return provider, digest

    def peek(self, provider, key, management_key=None):
        cache_key = self.cache_key(provider, key, management_key)
        with self._guard:
            item = self._cache.get(cache_key)
            return deepcopy(item[1]) if item and item[0] > self.clock() else None

    def invalidate(self, provider):
        with self._guard:
            for key in list(self._cache):
                if key[0] == provider:
                    self._cache.pop(key)

    def get(self, url, key):
        try:
            status, data = self.transport(url, key)
            return status, data if isinstance(data, dict) else {}
        except Exception:
            return 0, {}

    def report(self, provider, key, management_key=None):
        if provider not in ENDPOINTS:
            raise ValueError("Unsupported allowance provider")
        cached = self.peek(provider, key, management_key)
        if cached is not None:
            return cached
        cache_key = self.cache_key(provider, key, management_key)
        with self._guard:
            lock = self._locks.setdefault(cache_key, threading.Lock())
        # Deduplicate concurrent page loads without blocking inference's cache peek.
        with lock:
            cached = self.peek(provider, key, management_key)
            if cached is not None:
                return cached
            result = self.fetch(provider, key, management_key)
            with self._guard:
                self._cache[cache_key] = (self.clock() + CACHE_SECONDS, result)
            return deepcopy(result)

    def fetch(self, provider, key, management_key):
        result = {
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "unavailable",
            "balance_status": "unavailable",
            "key_status": "not_supported" if provider == "routeway" else "unavailable",
        }
        endpoints = ENDPOINTS[provider]
        if provider == "openrouter":
            status, body = self.get(endpoints["key"], key)
            data = body.get("data")
            if (
                status == 200
                and isinstance(data, dict)
                and any(
                    number(data.get(field)) is not None
                    for field in ("usage", "limit", "limit_remaining")
                )
            ):
                result["key_status"] = "available"
                limit = number(data.get("limit"))
                used = number(data.get("usage"))
                remaining = number(data.get("limit_remaining"))
                reset = data.get("limit_reset")
                scope = "key"
                budget = data.get("effective_budget")
                if (
                    isinstance(budget, dict)
                    and number(budget.get("limit_usd")) is not None
                ):
                    effective_remaining = number(budget.get("remaining_usd"))
                    if limit is None or (
                        effective_remaining is not None
                        and (remaining is None or effective_remaining < remaining)
                    ):
                        limit, used, remaining = (
                            number(budget.get("limit_usd")),
                            number(budget.get("spend_usd")),
                            effective_remaining,
                        )
                        reset, scope = budget.get("reset_interval"), "effective"
                result.update(
                    {
                        "spending_scope": scope,
                        "spending_limit_usd": limit,
                        "spending_used_usd": used,
                        "spending_remaining_usd": remaining,
                        "spending_percent": (
                            max(0, 100 * (limit - remaining) / limit)
                            if limit and remaining is not None
                            else (100.0 if limit == 0 else None)
                        ),
                        "limit_reset": (
                            reset
                            if isinstance(reset, str)
                            and reset in ("daily", "weekly", "monthly")
                            else None
                        ),
                        "key_usage_daily_usd": number(data.get("usage_daily")),
                    }
                )
        # Management credentials are separate; an inference key may still be allowed
        # to read credits (OpenRouter currently permits this on the connected account).
        status, body = self.get(endpoints["balance"], management_key or key)
        balance = None
        if status == 200:
            if provider == "routeway":
                balance = number(body.get("balance"))
            else:
                data = body.get("data")
                if isinstance(data, dict):
                    credits, used = number(data.get("total_credits")), number(
                        data.get("total_usage")
                    )
                    if credits is not None and used is not None:
                        balance = max(0, credits - used)
                        result.update(
                            account_credits_usd=credits, account_usage_usd=used
                        )
            if balance is not None:
                result.update(balance_remaining_usd=balance, balance_status="available")
        elif status in (401, 403):
            result["balance_status"] = "permission_required"
        if (
            result["balance_status"] == "available"
            and result["key_status"] != "unavailable"
        ):
            result["status"] = "available"
        elif (
            result["balance_status"] == "available"
            or result["key_status"] == "available"
        ):
            result["status"] = "partial"
        elif result["balance_status"] == "permission_required":
            result["status"] = "permission_required"
        return ProviderAllowance.model_validate(result).model_dump()


DEFAULT_REPORTER = AllowanceReporter()
