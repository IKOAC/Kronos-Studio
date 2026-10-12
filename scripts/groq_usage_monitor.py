#!/usr/bin/env python3
"""Local Groq quota observer. Records metadata only; never secrets or prompts."""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import ssl
import urllib.error
import urllib.request

HOME = pathlib.Path.home() / ".local" / "share" / "kronos-groq"
LOG = HOME / "usage.jsonl"
STATE = HOME / "alert_state.json"
MODEL = "openai/gpt-oss-120b"
DEFAULT_TOKEN_LIMIT = 200_000
DEFAULT_REQUEST_LIMIT = 1_000

def today():
    return dt.datetime.now(dt.timezone.utc).date().isoformat()

def load_records():
    if not LOG.exists():
        return []
    records = []
    with LOG.open(encoding="utf-8") as f:
        for row in f:
            try:
                item = json.loads(row)
                if item.get("date_utc") == today():
                    records.append(item)
            except (json.JSONDecodeError, ValueError):
                continue
    return records

def read_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}

def record(model, usage, headers, status_code):
    HEADERS = {k.lower(): v for k, v in (headers or {}).items()}
    details = (usage or {}).get("prompt_tokens_details") or {}
    cached = max(0, int(details.get("cached_tokens") or 0))
    prompt = max(0, int((usage or {}).get("prompt_tokens") or 0))
    completion = max(0, int((usage or {}).get("completion_tokens") or 0))
    event = {
        "at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "date_utc": today(),
        "model": model,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
        "billable_quota_tokens": max(0, prompt - cached) + completion,
        "status_code": int(status_code),
        "daily_requests_limit": HEADERS.get("x-ratelimit-limit-requests"),
        "daily_requests_remaining": HEADERS.get("x-ratelimit-remaining-requests"),
    }
    HOME.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, separators=(",", ":")) + "\n")
    LOG.chmod(0o600)
    return event

def report():
    rows = [r for r in load_records() if r.get("model") == MODEL]
    token_total = sum(int(r.get("billable_quota_tokens", 0)) for r in rows)
    # Every recorded attempt is a conservative lower bound on requests.
    # Provider checkpoints can decrease/reset and must not erase local calls.
    local_requests = len(rows)
    req_limit = DEFAULT_REQUEST_LIMIT
    authoritative_used = None
    uncertain_after_checkpoint = 0
    for index in range(len(rows) - 1, -1, -1):
        entry = rows[index]
        try:
            limit = int(entry.get("daily_requests_limit"))
            remaining = int(entry.get("daily_requests_remaining"))
            if limit > 0:
                req_limit = limit
                authoritative_used = max(0, limit - remaining)
                # Attempts without a provider response after the last genuine
                # rate-limit checkpoint are counted conservatively.
                uncertain_after_checkpoint = sum(1 for row in rows[index + 1:] if row.get("status_code") == 0)
                break
        except (TypeError, ValueError):
            pass
    used_requests = max(local_requests, authoritative_used + uncertain_after_checkpoint) if authoritative_used is not None else local_requests
    token_pct = 100 * token_total / DEFAULT_TOKEN_LIMIT
    request_pct = 100 * used_requests / req_limit
    overall_pct = max(token_pct, request_pct)
    current_bucket = min(100, int(overall_pct // 5) * 5)
    saved = read_state()
    previous_bucket = int(saved.get("last_notified_pct", 0)) if saved.get("date_utc") == today() else 0
    crossed = list(range(previous_bucket + 5, current_bucket + 1, 5))
    return {
        "model": MODEL,
        "date_utc": today(),
        "token_limit_assumed": DEFAULT_TOKEN_LIMIT,
        "tokens_observed": token_total,
        "token_percent_observed": round(token_pct, 2),
        "requests_limit": req_limit,
        "requests_used": used_requests,
        "requests_percent_used": round(request_pct, 2),
        "requests_source": "Groq response rate-limit header" if authoritative_used is not None else "locally recorded calls only",
        "percentage_for_alerts": round(overall_pct, 2),
        "pending_5pct_alerts": crossed,
        "last_notified_pct": previous_bucket,
        "coverage": "Token tally covers only calls sent through this local recorder; other API clients are not included. Account-specific limits may differ.",
    }

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    ack = sub.add_parser("ack")
    ack.add_argument("--through", type=int, required=True)
    sub.add_parser("record")  # JSON {model,usage,headers,status_code} via stdin
    sub.add_parser("request") # Groq POST body via stdin; env or private local credential file
    args = parser.parse_args()
    if args.command == "record":
        p = json.load(sys.stdin)
        record(p.get("model", MODEL), p.get("usage"), p.get("headers"), p.get("status_code", 200))
        print(json.dumps(report(), indent=2))
    elif args.command == "request":
        key = os.environ.get("GROQ_API_KEY", "").strip()
        if not key:
            secret_file = pathlib.Path.home() / ".config" / "kronos-studio" / "groq_key"
            if secret_file.is_file() and not (secret_file.stat().st_mode & 0o077):
                key = secret_file.read_text(encoding="ascii").strip()
        if not key:
            raise SystemExit("Private Groq key not found; no API request sent")
        payload = json.load(sys.stdin)
        model = payload.get("model", MODEL)
        url = "https://api.groq.com/openai/v1/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "KronosStudioResearch/0.1"},
            method="POST",
        )
        code, response, headers = 0, {}, {}
        try:
            with urllib.request.urlopen(req, timeout=120, context=ssl.create_default_context(cafile="/etc/ssl/cert.pem")) as resp:
                code = resp.status
                headers = dict(resp.headers.items())
                response = json.load(resp)
        except urllib.error.HTTPError as err:
            code = err.code
            headers = dict(err.headers.items())
            try:
                response = json.loads(err.read().decode("utf-8"))
            except ValueError:
                response = {"error": "Non-JSON provider error"}
        finally:
            record(model, response.get("usage") if isinstance(response, dict) else {}, headers, code)
        print(json.dumps({"http_status": code, "response": response, "quota": report()}, indent=2))
        if code >= 400:
            raise SystemExit(1)
    elif args.command == "status":
        print(json.dumps(report(), indent=2))
    elif args.command == "ack":
        result = report()
        mark = args.through
        if mark < 0 or mark > 100 or mark % 5 or mark > int(result["percentage_for_alerts"] // 5) * 5:
            raise SystemExit("Cannot acknowledge a milestone that has not been reached.")
        STATE.write_text(json.dumps({"date_utc": today(), "last_notified_pct": mark}) + "\n", encoding="utf-8")
        STATE.chmod(0o600)
        print(json.dumps({"acknowledged_through_pct": mark, "date_utc": today()}))

if __name__ == "__main__":
    main()
