"""Groq-only OSS-120B analysis with metered JSON recovery and bounded pacing."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import ssl
import stat
import tempfile
import time
import urllib.error
import urllib.request

from schemas.groq_analysis import GROQ_MODEL, GroqQuota
from services.groq_analysis import (
    GroqAnalysisError,
    GroqAnalysisService,
    GroqSession,
    MAX_COMPLETION_TOKENS,
    MAX_PROMPT_BYTES,
    _private_directory,
    _private_file,
)


@dataclass(frozen=True)
class Provider:
    name: str
    url: str
    model: str
    env: str


PROVIDERS = (
    Provider(
        "groq",
        "https://api.groq.com/openai/v1/chat/completions",
        GROQ_MODEL,
        "GROQ_API_KEY",
    ),
)
# Only provider aliases for the same 120B model, never another size or model.
MODEL_IDENTITIES = frozenset({GROQ_MODEL})


def now_utc():
    return datetime.now(timezone.utc).date().isoformat()


def unavailable(code="GROQ_UPSTREAM_ERROR", status=503):
    return GroqAnalysisError(
        status,
        code,
        "Groq is currently unavailable for OSS-120B analysis.",
    )


class ProviderJournal:
    """Private metadata only. Unknown provider allowances stay unknown."""

    def __init__(self, root: Path):
        self.root = root
        self.log = root / "usage.jsonl"
        self.state = root / "availability.json"

    def ensure(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not _private_directory(self.root):
            raise GroqAnalysisError(
                503, "TRACKER_UNAVAILABLE", "Provider usage directory is not private."
            )

    def read(self, path, default):
        if not path.exists():
            return default
        if not _private_directory(path.parent) or not _private_file(path):
            raise GroqAnalysisError(
                503, "TRACKER_UNAVAILABLE", "Provider usage files are not private."
            )
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise GroqAnalysisError(
                503,
                "TRACKER_UNAVAILABLE",
                "Provider availability state cannot be read.",
            ) from exc

    def rows(self):
        if not self.log.exists():
            return []
        if not _private_directory(self.root) or not _private_file(self.log):
            raise GroqAnalysisError(
                503, "TRACKER_UNAVAILABLE", "Provider usage log is not private."
            )
        try:
            return [
                json.loads(line)
                for line in self.log.read_text().splitlines()
                if line.strip()
            ]
        except (OSError, ValueError) as exc:
            raise GroqAnalysisError(
                503, "TRACKER_UNAVAILABLE", "Provider usage cannot be read."
            ) from exc

    def quota(self, provider, limits=None):
        rows = [
            r
            for r in self.rows()
            if r["provider"] == provider and r["day_utc"] == now_utc()
        ]
        tokens = sum(r["tokens"] for r in rows)
        limits = limits or {}
        token_limit, request_limit = limits.get("tokens"), limits.get("requests")
        token_pct = 100 * tokens / token_limit if token_limit else None
        request_pct = 100 * len(rows) / request_limit if request_limit else None
        percentages = [p for p in (token_pct, request_pct) if p is not None]
        return GroqQuota(
            day_utc=now_utc(),
            token_limit_assumed=token_limit,
            tokens_observed=tokens,
            token_percent_observed=token_pct,
            requests_limit=request_limit,
            requests_used=len(rows),
            requests_percent_used=request_pct,
            usage_percent=max(percentages) if percentages else None,
            cap_percent=80,
            pending_5pct_alerts=[],
        )

    def record(
        self, provider, usage, status, estimated_tokens, *, generation_failed=False
    ):
        self.ensure()
        known = isinstance(usage, dict) and all(
            isinstance(usage.get(k), int)
            and not isinstance(usage.get(k), bool)
            and usage[k] >= 0
            for k in ("prompt_tokens", "completion_tokens")
        )
        if known:
            tokens = usage["prompt_tokens"] + usage["completion_tokens"]
            if provider == "groq":
                cached = (usage.get("prompt_tokens_details") or {}).get(
                    "cached_tokens", 0
                )
                if isinstance(cached, int):
                    tokens -= min(max(0, cached), usage["prompt_tokens"])
        else:
            tokens = estimated_tokens if status in (0, 200) or generation_failed else 0
        cost = usage.get("cost") if isinstance(usage, dict) else None
        if not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
            cost = None
        event = {
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "day_utc": now_utc(),
            "provider": provider,
            "model": GROQ_MODEL,
            "tokens": tokens,
            "estimated": not known and (status in (0, 200) or generation_failed),
            "http_status": status,
            "reported_cost": cost,
        }
        try:
            fd = os.open(
                str(self.log),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,
                0o600,
            )
            with os.fdopen(fd, "a") as file:
                if not _private_file(self.log):
                    raise OSError("private log required")
                file.write(json.dumps(event, separators=(",", ":")) + "\n")
        except OSError as exc:
            raise GroqAnalysisError(
                503, "TRACKER_UNAVAILABLE", "Could not record provider usage."
            ) from exc
        return tokens

    def blocked(self, provider):
        state = self.read(self.state, {})
        item = state.get(provider, {})
        return item if item.get("until", 0) > time.time() else None

    def block(self, provider, seconds, reason):
        self.ensure()
        state = self.read(self.state, {})
        state[provider] = {"until": time.time() + max(1, seconds), "reason": reason}
        fd, temporary = tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd, "w") as file:
                json.dump(state, file)
            os.replace(temporary, self.state)
        finally:
            Path(temporary).unlink(missing_ok=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class ProviderAnalysisService(GroqAnalysisService):
    def __init__(
        self,
        *,
        key_directory=None,
        journal_root=None,
        provider_transport=None,
        groq_tracker=None,
        lock_path=None,
    ):
        super().__init__(tracker=groq_tracker, lock_path=lock_path)
        self.key_directory = key_directory or Path.home() / ".config" / "kronos-studio"
        self.journal = ProviderJournal(
            journal_root or Path.home() / ".local" / "share" / "kronos-ai"
        )
        self.provider_transport = provider_transport or self.send_provider

    def key(self, provider):
        key = os.environ.get(provider.env, "").strip()
        if not key:
            path = self.key_directory / (provider.name + "_key")
            if not _private_directory(path.parent) or not _private_file(path):
                raise unavailable("PROVIDER_NOT_CONFIGURED")
            try:
                key = path.read_text(encoding="ascii").strip()
            except (OSError, UnicodeError) as exc:
                raise unavailable("PROVIDER_NOT_CONFIGURED") from exc
        if len(key) < 20 or not key.isascii() or "\n" in key or "\r" in key:
            raise unavailable("PROVIDER_NOT_CONFIGURED")
        return key

    def limits(self, provider):
        path = self.key_directory / "provider_limits.json"
        if not path.exists():
            return {}
        data = self.journal.read(path, {}).get(provider, {})
        if not isinstance(data, dict) or any(
            not isinstance(v, int) or isinstance(v, bool) or v <= 0
            for k, v in data.items()
            if k in ("tokens", "requests")
        ):
            raise GroqAnalysisError(
                503,
                "TRACKER_UNAVAILABLE",
                "Provider allowance configuration is invalid.",
            )
        return {k: v for k, v in data.items() if k in ("tokens", "requests")}

    def provider_quota(self, provider):
        if provider == "groq":
            return super()._quota(self._monitor())[1]
        return self.journal.quota(provider, self.limits(provider))

    def _quota(self, tracker):
        if isinstance(tracker, str):
            quota = self.provider_quota(tracker)
            return quota.model_dump(), quota
        return super()._quota(tracker)

    def statuses(self):
        result = []
        for provider in PROVIDERS:
            configured = True
            quota = None
            failure_reason = None
            try:
                credential = self.key(provider)
            except GroqAnalysisError:
                configured = False
            status = "not_configured" if not configured else "ready"
            try:
                quota = self.provider_quota(provider.name)
                if (
                    configured
                    and quota.usage_percent is not None
                    and quota.usage_percent >= quota.cap_percent
                ):
                    status = "quota_exhausted"
                block = self.journal.blocked(provider.name)
                if configured and block:
                    status = "cooldown"
                    failure_reason = block.get("reason")
                    if failure_reason not in {
                        "exhausted",
                        "unavailable",
                        "model_mismatch",
                        "model_unavailable",
                        "request_rejected",
                        "transport_error",
                    }:
                        failure_reason = "unavailable"
            except GroqAnalysisError:
                if configured:
                    status = "tracker_unavailable"
            result.append(
                {
                    "provider": provider.name,
                    "model": provider.model,
                    "configured": configured,
                    "status": status,
                    "failure_reason": failure_reason,
                    "quota": quota.model_dump() if quota else None,
                }
            )
        return {
            "model": GROQ_MODEL,
            "fallback_order": [p.name for p in PROVIDERS],
            "providers": result,
        }

    @staticmethod
    def wire_payload(provider, payload):
        if payload.get("model") != GROQ_MODEL:
            raise GroqAnalysisError(
                500, "MODEL_NOT_ALLOWED", "Only GPT-OSS-120B is permitted."
            )
        body = json.loads(json.dumps(payload))
        body["model"] = provider.model
        for name in ("models", "route", "fallbacks", "preset", "provider", "api_key"):
            body.pop(name, None)
        return body

    @staticmethod
    def json_recovery_payload(body):
        body = json.loads(json.dumps(body))
        schema = body["response_format"]["json_schema"]["schema"]
        body["response_format"] = {"type": "json_object"}
        body["messages"][0][
            "content"
        ] += " Return JSON matching this schema: " + json.dumps(
            schema, separators=(",", ":")
        )
        body["reasoning_format"] = "hidden"
        return body

    @staticmethod
    def send_provider(provider, payload, key):
        context = ssl.create_default_context(
            cafile="/etc/ssl/cert.pem" if Path("/etc/ssl/cert.pem").is_file() else None
        )
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context), NoRedirect()
        )
        request = urllib.request.Request(
            provider.url,
            data=json.dumps(payload, separators=(",", ":")).encode(),
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "User-Agent": "KronosStudioResearch/0.3",
            },
            method="POST",
        )
        try:
            with opener.open(request, timeout=45) as response:
                return (
                    response.status,
                    json.load(response),
                    dict(response.headers.items()),
                )
        except urllib.error.HTTPError as exc:
            # Classify errors without retaining upstream text, prompts or credentials.
            code = "request_rejected"
            try:
                data = json.loads(exc.read(65536))
                error = data.get("error", {}) if isinstance(data, dict) else {}
                message = (
                    str(error.get("message", "")).lower()
                    if isinstance(error, dict)
                    else ""
                )
                if (
                    isinstance(error, dict)
                    and error.get("code") == "json_validate_failed"
                ):
                    code = "output_invalid"
                elif (
                    exc.code == 404
                    or "no model found" in message
                    or "unavailable for free" in message
                ):
                    code = "model_unavailable"
            except (OSError, ValueError, TypeError):
                pass
            return exc.code, {"error": {"code": code}}, dict(exc.headers.items())
        except (OSError, TimeoutError, ValueError, urllib.error.URLError) as exc:
            raise GroqAnalysisError(
                502,
                "GROQ_TRANSPORT_ERROR",
                "The provider did not return a usable response.",
            ) from exc

    @contextmanager
    def session(self, *, reserved_tokens, max_requests):
        self.journal.ensure()
        self.journal.rows()
        self.lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not _private_directory(self.lock_path.parent):
            raise unavailable("TRACKER_UNAVAILABLE")
        try:
            fd = os.open(
                str(self.lock_path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
            )
        except OSError as exc:
            raise unavailable("TRACKER_UNAVAILABLE") from exc
        with os.fdopen(fd, "r+") as lock:
            if not _private_file(self.lock_path):
                raise unavailable("TRACKER_UNAVAILABLE")
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield ProviderSession(self, reserved_tokens, max_requests)


class ProviderSession:
    def __init__(self, service, reservation, max_turns):
        self.service, self.reservation, self.max_turns = service, reservation, max_turns
        self.turns_started = 0
        self.requests_sent = self.tokens_used = 0
        self.provider = "groq"
        self.providers_used = []
        self.attempts = []
        self.rate_headers = {}
        self.rate_checked_at = 0.0
        self.max_refill_wait = 45

    @property
    def tracker(self):
        return self.provider

    def budget(self, name, tokens, requests):
        quota = self.service.provider_quota(name)
        return not (
            (
                quota.token_limit_assumed is not None
                and quota.tokens_observed + tokens
                > quota.token_limit_assumed * quota.cap_percent / 100
            )
            or (
                quota.requests_limit is not None
                and quota.requests_used + requests
                > quota.requests_limit * quota.cap_percent / 100
            )
        )

    def complete(self, payload, allowed_facts):
        if self.turns_started >= self.max_turns:
            raise GroqAnalysisError(
                429, "AGENT_RUN_LIMIT", "The bounded analysis turn limit was reached."
            )
        payload_bytes = len(json.dumps(payload, separators=(",", ":")).encode())
        if (
            payload_bytes > MAX_PROMPT_BYTES
            or payload.get("max_completion_tokens") != MAX_COMPLETION_TOKENS
        ):
            raise GroqAnalysisError(
                422, "ANALYSIS_TOO_LARGE", "The research snapshot is too large."
            )
        self.turns_started += 1
        remaining_turns = self.max_turns - self.turns_started + 1
        reserve = math.ceil(self.reservation * remaining_turns / self.max_turns)
        candidates = list(PROVIDERS)
        if self.providers_used:
            candidates.sort(key=lambda p: p.name != self.provider)
        recovery_pending = False
        generation_failed_this_turn = False
        retry_used = False
        for candidate_index, provider in enumerate(candidates):
            name = provider.name
            try:
                key = self.service.key(provider)
                block = self.service.journal.blocked(name)
                if block:
                    if block.get("reason") == "exhausted":
                        raise GroqAnalysisError(
                            429,
                            "GROQ_RATE_LIMITED",
                            "Groq is waiting for its quota to reset.",
                        )
                    continue
                if not self.budget(name, reserve, remaining_turns):
                    raise GroqAnalysisError(
                        429,
                        "GROQ_DAILY_CAP",
                        "The analysis would exceed Groq's daily usage ceiling.",
                    )
            except GroqAnalysisError as exc:
                if exc.code != "PROVIDER_NOT_CONFIGURED":
                    raise
                continue
            body = self.service.wire_payload(provider, payload)
            recovering = recovery_pending and name == "groq"
            if recovering:
                recovery_pending = False
                body = self.service.json_recovery_payload(body)
                if len(json.dumps(body).encode()) > MAX_PROMPT_BYTES:
                    continue
            # Include the structured-output schema in the input estimate. It
            # consumes allowance too, even though it is outside the messages.
            needed_tokens = len(json.dumps(body).encode()) // 2 + MAX_COMPLETION_TOKENS
            GroqSession._pace(self, needed_tokens)
            try:
                if (
                    int(self.rate_headers.get("x-ratelimit-remaining-requests", "1"))
                    <= 0
                ):
                    raise GroqAnalysisError(
                        429,
                        "GROQ_RATE_LIMITED",
                        "Groq's request allowance is exhausted.",
                    )
            except (ValueError, TypeError):
                pass
            self.requests_sent += 1
            try:
                status, response, headers = self.service.provider_transport(
                    provider, body, key
                )
            except Exception:
                # A transport failure may still have consumed quota; meter the
                # uncertain attempt conservatively before trying another provider.
                status, response, headers = 0, {}, {}
            usage = response.get("usage") if isinstance(response, dict) else None
            error = response.get("error", {}) if isinstance(response, dict) else {}
            generation_failed = (
                status == 400
                and name == "groq"
                and isinstance(error, dict)
                and error.get("code") == "output_invalid"
            )
            estimated = len(json.dumps(body).encode()) + MAX_COMPLETION_TOKENS
            self.tokens_used += self.service.journal.record(
                name, usage, status, estimated, generation_failed=generation_failed
            )
            if name == "groq":
                recorded_usage = (
                    usage
                    if isinstance(usage, dict)
                    and all(
                        isinstance(usage.get(k), int) and usage[k] >= 0
                        for k in ("prompt_tokens", "completion_tokens")
                    )
                    else (
                        {
                            "prompt_tokens": len(json.dumps(body).encode()),
                            "completion_tokens": MAX_COMPLETION_TOKENS,
                        }
                        if status in (0, 200) or generation_failed
                        else {}
                    )
                )
                try:
                    self.service._monitor().record(
                        GROQ_MODEL, recorded_usage, headers, status
                    )
                except Exception as exc:
                    raise unavailable("TRACKER_UNAVAILABLE") from exc
            if generation_failed:
                generation_failed_this_turn = True
                self.attempts.append(
                    {"provider": name, "http_status": status, "status": "unavailable"}
                )
                # Exactly one format recovery, metered and checked against the quota.
                # Output-generation failure does not establish a provider outage.
                if not retry_used:
                    retry_used = True
                    recovery_pending = True
                    candidates.insert(candidate_index + 1, provider)
                continue
            if status in (502, 503, 504) and not retry_used:
                # One bounded retry for an upstream gateway failure. Rate-limit
                # and credit failures are never retried here.
                retry_used = True
                self.attempts.append(
                    {"provider": name, "http_status": status, "status": "unavailable"}
                )
                time.sleep(1)
                candidates.insert(candidate_index + 1, provider)
                continue
            if status != 200:
                seconds = 3600 if status == 402 else 60
                if status == 429:
                    try:
                        seconds = max(
                            1,
                            min(
                                86400,
                                float(
                                    headers.get(
                                        "retry-after", headers.get("Retry-After", 60)
                                    )
                                ),
                            ),
                        )
                    except (ValueError, TypeError):
                        pass
                reason = (
                    "exhausted"
                    if status in (402, 429)
                    else "transport_error" if status == 0 else "unavailable"
                )
                if status in (400, 404, 422):
                    error = (
                        response.get("error", {}) if isinstance(response, dict) else {}
                    )
                    reason = (
                        "model_unavailable"
                        if status == 404
                        or (
                            isinstance(error, dict)
                            and error.get("code") == "model_unavailable"
                        )
                        else "request_rejected"
                    )
                self.service.journal.block(name, seconds, reason)
                self.attempts.append(
                    {
                        "provider": name,
                        "http_status": status,
                        "status": (
                            "exhausted" if status in (402, 429) else "unavailable"
                        ),
                    }
                )
                continue
            if (
                not isinstance(response, dict)
                or response.get("model") not in MODEL_IDENTITIES
            ):
                self.service.journal.block(name, 3600, "model_mismatch")
                self.attempts.append(
                    {
                        "provider": name,
                        "http_status": status,
                        "status": "model_mismatch",
                    }
                )
                continue
            findings = self.service.validate_findings(response, allowed_facts)
            self.provider = name
            if name not in self.providers_used:
                self.providers_used.append(name)
            self.rate_headers = {
                k.lower(): str(v)
                for k, v in headers.items()
                if k.lower().startswith("x-ratelimit-")
            }
            self.rate_checked_at = time.monotonic()
            self.attempts.append(
                {"provider": name, "http_status": status, "status": "succeeded"}
            )
            return findings
        if generation_failed_this_turn:
            raise GroqAnalysisError(
                502,
                "GROQ_INVALID_OUTPUT",
                "The provider could not generate valid analysis JSON.",
            )
        blocks = [self.service.journal.blocked(p.name) for p in PROVIDERS]
        reasons = {block.get("reason") for block in blocks if block}
        if "transport_error" in reasons:
            raise unavailable("GROQ_TRANSPORT_ERROR", status=502)
        if "request_rejected" in reasons:
            raise GroqAnalysisError(
                502,
                "PROVIDER_REQUEST_REJECTED",
                "A provider rejected the analysis request.",
            )
        if "exhausted" in reasons:
            raise GroqAnalysisError(
                429, "GROQ_RATE_LIMITED", "Groq is rate limiting analysis requests."
            )
        if "model_mismatch" in reasons:
            raise unavailable("MODEL_NOT_ALLOWED", status=502)
        if "model_unavailable" in reasons:
            raise GroqAnalysisError(
                503,
                "GROQ_MODEL_UNAVAILABLE",
                "Groq is not serving the configured OSS-120B model.",
            )
        raise unavailable(status=502)
