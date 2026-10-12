"""Secure, metered Groq analysis of independently calculated financial metrics.

The external quota recorder is mandatory. Failure to load it blocks requests.
No API key, user candle history, model content, or prompts are logged.
"""

from __future__ import annotations

from contextlib import contextmanager

import fcntl
import importlib.util
import json
import os
import re
import time
import ssl
import stat
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from schemas.financial_analysis import FinancialAnalysisResponse
from schemas.groq_analysis import (
    GROQ_MODEL,
    GroqAnalysisRequest,
    GroqFindings,
    GroqQuota,
)
from services.financial_analysis.engine import analyze_financials

API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_CAP_PERCENT = 80.0
MAX_COMPLETION_TOKENS = 850
MAX_PROMPT_BYTES = 18_000

FINDINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "supporting_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "conflicting_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary",
        "supporting_evidence_ids",
        "conflicting_evidence_ids",
        "limitations",
    ],
}


class GroqAnalysisError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _private_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.getuid()
        and info.st_mode & 0o077 == 0
    )


def _private_directory(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and info.st_uid == os.getuid()
        and info.st_mode & 0o077 == 0
    )


class GroqAnalysisService:
    def __init__(
        self,
        *,
        tracker: Any = None,
        transport: Any = None,
        key_path: Path | None = None,
        lock_path: Path | None = None,
        cap_percent: float = DEFAULT_CAP_PERCENT,
    ):
        if not 0 < cap_percent <= 80:
            raise ValueError("The configured cap must be in (0, 80].")
        self.tracker = tracker
        self.transport = transport or self._send
        self.key_path = (
            key_path or Path.home() / ".config" / "kronos-studio" / "groq_key"
        )
        self.lock_path = (
            lock_path
            or Path.home() / ".local" / "share" / "kronos-groq" / "analysis.lock"
        )
        self.cap_percent = cap_percent

    def _monitor(self):
        if self.tracker is not None:
            return self.tracker
        root = Path.home() / ".local" / "share" / "kronos-groq"
        monitor_path = root / "monitor.py"
        if not _private_directory(root):
            raise GroqAnalysisError(
                503,
                "TRACKER_UNAVAILABLE",
                "Private Groq quota directory is unavailable.",
            )
        if not monitor_path.is_file() or monitor_path.is_symlink():
            raise GroqAnalysisError(
                503, "TRACKER_UNAVAILABLE", "The Groq quota tracker is unavailable."
            )
        try:
            spec = importlib.util.spec_from_file_location(
                "kronos_private_usage_monitor", monitor_path
            )
            if spec is None or spec.loader is None:
                raise ImportError("Unable to load tracker.")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if not all(
                callable(getattr(module, name, None)) for name in ("report", "record")
            ):
                raise ImportError("Quota tracker is missing required functions.")
            return module
        except (OSError, ImportError) as exc:
            raise GroqAnalysisError(
                503,
                "TRACKER_UNAVAILABLE",
                "The Groq quota tracker failed to initialize.",
            ) from exc

    def _read_key(self) -> str:
        if not _private_directory(self.key_path.parent) or not _private_file(
            self.key_path
        ):
            raise GroqAnalysisError(
                503,
                "GROQ_NOT_CONFIGURED",
                "A private Groq API credential is not configured.",
            )
        try:
            key = self.key_path.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError) as exc:
            raise GroqAnalysisError(
                503, "GROQ_NOT_CONFIGURED", "Cannot read the private Groq credential."
            ) from exc
        if not key.startswith("gsk_") or len(key) < 24:
            raise GroqAnalysisError(
                503, "GROQ_NOT_CONFIGURED", "Invalid private Groq credential format."
            )
        return key

    def _send(self, payload: dict, key: str) -> tuple[int, dict, dict]:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            API_URL,
            data=data,
            method="POST",
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "User-Agent": "KronosStudioResearch/0.2",
            },
        )
        ca_file = Path("/etc/ssl/cert.pem")
        context = ssl.create_default_context(
            cafile=str(ca_file) if ca_file.is_file() else None
        )
        try:
            with urllib.request.urlopen(
                request, timeout=30, context=context
            ) as response:
                status = response.status
                headers = dict(response.headers.items())
                body = json.load(response)
                return status, body, headers
        except urllib.error.HTTPError as exc:
            # Do not include the provider's error body; it may echo sensitive data.
            return exc.code, {}, dict(exc.headers.items())
        except (TimeoutError, OSError, ValueError, urllib.error.URLError) as exc:
            # A request may have reached the provider even if we could not read a response.
            raise GroqAnalysisError(
                502, "GROQ_TRANSPORT_ERROR", "Groq did not return a usable response."
            ) from exc

    def _allowed_facts(self, metrics: FinancialAnalysisResponse) -> dict[str, Any]:
        facts = {
            "technical." + name: value
            for name, value in metrics.technical.model_dump().items()
            if value is not None
        }
        if metrics.forecast is not None:
            forecast = metrics.forecast
            for key in (
                "direction_counts",
                "majority_direction",
                "agreement_pct",
                "mean_change_pct",
                "median_change_pct",
                "dispersion_std_pct",
                "change_range_pct",
            ):
                value = getattr(forecast, key)
                if value is not None:
                    facts["forecast." + key] = value
            for item in forecast.models:
                facts["forecast.model." + item.model_name] = {
                    "change_pct": item.change_pct,
                    "direction": item.direction,
                }
        if metrics.trade is not None:
            for key, value in metrics.trade.model_dump().items():
                if value is not None:
                    facts["trade." + key] = value
        return facts

    def _make_prompt(
        self, metrics: FinancialAnalysisResponse, symbol: str, interval: str
    ):
        facts = self._allowed_facts(metrics)
        consensus = self._consensus(metrics)
        context = {
            "symbol": symbol,
            "interval": interval,
            "forecast_consensus": consensus,
            "evidence": facts,
        }
        system = (
            "You analyze an immutable numerical snapshot for read-only market research. "
            "The numerical calculations were performed by code and must not be altered. "
            "This snapshot uses supplied completed candles and does not update continuously. It is not an investment recommendation. "
            "Do not suggest BUY, SELL, orders, entries, stop losses, profit targets, "
            "probabilities of success, or claims of historical accuracy. "
            "Use only evidence identifiers supplied in the evidence object. "
            "Return a short objective summary without any digits or numerical values; "
            "do not introduce information absent from the evidence. "
            "Supporting and conflicting identifiers must each be a subset of available "
            "evidence keys, with no duplicates and no overlap. "
            "Forecasts are optional. When no forecasts are supplied, assess the technical evidence alone; do not request predictions or imply forecast agreement. "
            "If supplied forecasts disagree or data are insufficient, explicitly acknowledge uncertainty. "
            "Keep the summary under two hundred twenty characters, using at most two short sentences. Use at most two distinct supporting and two distinct conflicting evidence IDs, with no overlap. List no more than three concise limitations. Do not write any digits in the summary or limitations. Return only the required JSON fields."
        )
        body = json.dumps(context, separators=(",", ":"), ensure_ascii=True)
        # Groq strict mode supports enum constraints. Length, uniqueness and
        # narrative checks remain independently enforced by Python validators.
        schema = json.loads(json.dumps(FINDINGS_SCHEMA))
        schema["properties"]["summary"][
            "description"
        ] = "At most two short sentences, under two hundred twenty characters. No digits or numeric indicator labels."
        for name in ("supporting_evidence_ids", "conflicting_evidence_ids"):
            schema["properties"][name]["items"]["enum"] = list(facts)
            schema["properties"][name][
                "description"
            ] = "At most two distinct supplied evidence IDs. No overlap with the other evidence list."
        schema["properties"]["limitations"]["items"]["enum"] = [
            "Forecast agreement does not establish accuracy.",
            "Historical indicators do not guarantee future outcomes.",
            "News, sentiment, and fundamentals were not supplied.",
            "Latest completed candles are used; the forming candle is excluded.",
            "Portfolio holdings and execution conditions were not supplied.",
            "Technical indicators can conflict with model forecasts.",
        ]
        if metrics.forecast is None:
            schema["properties"]["limitations"]["items"]["enum"] = [
                value
                for value in schema["properties"]["limitations"]["items"]["enum"]
                if "forecast" not in value.lower()
            ]
        schema["properties"]["limitations"][
            "description"
        ] = "Choose at most three applicable limitations."
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": body},
            ],
            "reasoning_effort": "low",
            "temperature": 0,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "kronos_research_analysis",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        serialized = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(serialized) > MAX_PROMPT_BYTES:
            raise GroqAnalysisError(
                422,
                "ANALYSIS_TOO_LARGE",
                "The requested research snapshot is too large.",
            )
        return payload, facts, len(serialized)

    @staticmethod
    def _consensus(metrics: FinancialAnalysisResponse) -> str:
        if metrics.forecast is None or len(metrics.forecast.models) < 2:
            return "insufficient"
        return metrics.forecast.majority_direction or "mixed"

    def _quota(self, tracker) -> tuple[dict, GroqQuota]:
        try:
            status = tracker.report()
            info = GroqQuota(
                day_utc=status["date_utc"],
                token_limit_assumed=status["token_limit_assumed"],
                tokens_observed=status["tokens_observed"],
                token_percent_observed=status["token_percent_observed"],
                requests_limit=status["requests_limit"],
                requests_used=status["requests_used"],
                requests_percent_used=status["requests_percent_used"],
                usage_percent=status["percentage_for_alerts"],
                cap_percent=self.cap_percent,
                pending_5pct_alerts=status["pending_5pct_alerts"],
            )
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise GroqAnalysisError(
                503, "TRACKER_UNAVAILABLE", "Groq usage tracking is unavailable."
            ) from exc
        return status, info

    def get_quota(self) -> GroqQuota:
        _, info = self._quota(self._monitor())
        return info

    @contextmanager
    def session(self, *, reserved_tokens: int, max_requests: int):
        """Reserve a complete bounded run while holding the existing quota lock."""
        tracker = self._monitor()
        key = self._read_key()
        self.lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not _private_directory(self.lock_path.parent):
            raise GroqAnalysisError(
                503, "TRACKER_UNAVAILABLE", "Groq quota directory is not private."
            )
        try:
            fd = os.open(
                str(self.lock_path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
            )
        except OSError as exc:
            raise GroqAnalysisError(
                503, "TRACKER_UNAVAILABLE", "Groq quota lock is unavailable."
            ) from exc
        with os.fdopen(fd, "r+") as lock:
            if not _private_file(self.lock_path):
                raise GroqAnalysisError(
                    503, "TRACKER_UNAVAILABLE", "Groq quota lock is not private."
                )
            fcntl.flock(lock, fcntl.LOCK_EX)
            status, _ = self._quota(tracker)
            self._check_budget(status, reserved_tokens, max_requests)
            yield GroqSession(self, tracker, key, max_requests)

    def _check_budget(self, status: dict, tokens: int, requests: int):
        if (
            status["tokens_observed"] + tokens
            > status["token_limit_assumed"] * self.cap_percent / 100
            or status["requests_used"] + requests
            > status["requests_limit"] * self.cap_percent / 100
        ):
            raise GroqAnalysisError(
                429,
                "GROQ_DAILY_CAP",
                "Groq's configured daily usage cap would be exceeded.",
            )

    @staticmethod
    def validate_findings(response: dict, allowed_facts: dict) -> GroqFindings:
        try:
            choice = response["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("Response did not complete.")
            findings = GroqFindings.model_validate(
                json.loads(choice["message"]["content"])
            )
            identifiers = (
                findings.supporting_evidence_ids + findings.conflicting_evidence_ids
            )
            if any(evidence not in allowed_facts for evidence in identifiers):
                raise ValueError("Unknown evidence identifier.")
            if set(findings.supporting_evidence_ids) & set(
                findings.conflicting_evidence_ids
            ):
                raise ValueError("Overlapping evidence allocation.")
            return findings
        except (
            KeyError,
            IndexError,
            AttributeError,
            ValueError,
            TypeError,
            ValidationError,
        ) as exc:
            raise GroqAnalysisError(
                502,
                "GROQ_INVALID_OUTPUT",
                "Groq returned an invalid or unsupported analysis.",
            ) from exc

    def analyze(self, request: GroqAnalysisRequest) -> dict:
        metrics = FinancialAnalysisResponse.model_validate(analyze_financials(request))
        payload, allowed_facts, payload_bytes = self._make_prompt(
            metrics, request.symbol, request.interval
        )
        reserve = payload_bytes + MAX_COMPLETION_TOKENS + 512
        with self.session(reserved_tokens=reserve, max_requests=1) as session:
            findings = session.complete(payload, allowed_facts)
            _, quota = self._quota(session.tracker)
        return {
            "symbol": request.symbol,
            "interval": request.interval,
            "provider": getattr(session, "provider", "groq"),
            "model": GROQ_MODEL,
            "metrics": metrics,
            "findings": findings,
            "forecast_consensus": self._consensus(metrics),
            "quota": quota,
            "providers_used": getattr(session, "providers_used", ["groq"]),
            "provider_attempts": getattr(session, "attempts", []),
        }


class GroqSession:
    """All single-agent and TradingAgents calls share this metered transport."""

    def __init__(
        self, service: GroqAnalysisService, tracker: Any, key: str, max_requests: int
    ):
        self.service, self.tracker, self._key = service, tracker, key
        self.max_requests = max_requests
        self.requests_sent = 0
        self.tokens_used = 0
        self.rate_headers = {}
        self.rate_checked_at = 0.0

    def _pace(self, estimated_tokens: int):
        """Honor provider TPM headers between turns, without resending a failed call."""
        try:
            limit = int(self.rate_headers["x-ratelimit-limit-tokens"])
            remaining = int(self.rate_headers["x-ratelimit-remaining-tokens"])
        except (KeyError, ValueError, TypeError):
            return
        if estimated_tokens > limit:
            raise GroqAnalysisError(
                429,
                "GROQ_RATE_LIMITED",
                "This research turn exceeds Groq's current minute allowance.",
            )
        if remaining >= estimated_tokens:
            return
        value = self.rate_headers.get("x-ratelimit-reset-tokens", "")
        units = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}
        parts = re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", value)
        if not parts:
            raise GroqAnalysisError(
                429, "GROQ_RATE_LIMITED", "Groq's minute allowance is exhausted."
            )
        reset = sum(float(number) * units[unit] for number, unit in parts)
        # The reset header describes refill to the full bucket. Only wait for
        # the deficit needed by the next bounded turn, not the whole bucket.
        needed = max(0, estimated_tokens - remaining)
        refill_needed = reset * needed / max(1, limit - remaining)
        delay = max(0, refill_needed - (time.monotonic() - self.rate_checked_at))
        if delay:
            delay += 0.05
        if delay > 30:
            raise GroqAnalysisError(
                429,
                "GROQ_RATE_LIMITED",
                "Groq's minute allowance requires a longer wait.",
            )
        if delay:
            time.sleep(delay)

    def complete(self, payload: dict, allowed_facts: dict) -> GroqFindings:
        if self.requests_sent >= self.max_requests:
            raise GroqAnalysisError(
                429,
                "AGENT_RUN_LIMIT",
                "The bounded analysis request limit was reached.",
            )
        payload_bytes = len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        if (
            payload_bytes > MAX_PROMPT_BYTES
            or payload.get("max_completion_tokens") != MAX_COMPLETION_TOKENS
        ):
            raise GroqAnalysisError(
                422,
                "ANALYSIS_TOO_LARGE",
                "The requested research snapshot is too large.",
            )
        status, before = self.service._quota(self.tracker)
        self.service._check_budget(
            status, payload_bytes + MAX_COMPLETION_TOKENS + 512, 1
        )
        conservative_usage = {
            "prompt_tokens": payload_bytes,
            "completion_tokens": MAX_COMPLETION_TOKENS,
        }
        # TPM pacing uses a cheap estimate of English/JSON message tokens. The
        # daily cap remains protected by the larger full-byte reservation above.
        message_bytes = sum(
            len(item["content"].encode("utf-8")) for item in payload["messages"]
        )
        self._pace((message_bytes + 1) // 2 + MAX_COMPLETION_TOKENS)
        self.requests_sent += 1
        try:
            http_status, response, headers = self.service.transport(payload, self._key)
        except Exception as exc:
            try:
                self.tracker.record(GROQ_MODEL, conservative_usage, {}, 0)
            except Exception as record_error:
                raise GroqAnalysisError(
                    503,
                    "TRACKER_UNAVAILABLE",
                    "Could not record an uncertain Groq request.",
                ) from record_error
            if isinstance(exc, GroqAnalysisError):
                raise
            raise GroqAnalysisError(
                502, "GROQ_TRANSPORT_ERROR", "Groq connection failed."
            ) from exc
        self.rate_headers = {
            k.lower(): str(v)
            for k, v in headers.items()
            if k.lower().startswith("x-ratelimit-")
        }
        self.rate_checked_at = time.monotonic()
        usage = response.get("usage") if isinstance(response, dict) else None
        if http_status == 200 and (
            not isinstance(usage, dict)
            or not all(
                isinstance(usage.get(k), int) and usage[k] >= 0
                for k in ("prompt_tokens", "completion_tokens")
            )
        ):
            usage = conservative_usage
        try:
            self.tracker.record(GROQ_MODEL, usage or {}, headers, http_status)
            _, after = self.service._quota(self.tracker)
            self.tokens_used += max(0, after.tokens_observed - before.tokens_observed)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise GroqAnalysisError(
                503, "TRACKER_UNAVAILABLE", "Groq response could not be metered."
            ) from exc
        if http_status == 429:
            raise GroqAnalysisError(
                429, "GROQ_RATE_LIMITED", "Groq rate-limited this request."
            )
        if http_status != 200:
            raise GroqAnalysisError(
                502, "GROQ_UPSTREAM_ERROR", "Groq rejected or failed this request."
            )
        return self.service.validate_findings(response, allowed_facts)
