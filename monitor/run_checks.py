"""Smoke checks against a running API. Exit code 1 if any check fails.

Env: BASE_URL, MONITOR_API_KEY, ALERT_WEBHOOK_URL, MAX_LATENCY_MS (default 5000).
Failures are appended to monitor/failures.jsonl; alerts are de-duplicated per check
for 30 minutes using monitor/alert_state.json.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor.alert import send_alert  # noqa: E402
from target_api.schemas import SummarizeResponse  # noqa: E402

HERE = Path(__file__).resolve().parent
FAILURES_FILE = Path(os.getenv("FAILURES_FILE", HERE / "failures.jsonl"))
STATE_FILE = Path(os.getenv("ALERT_STATE_FILE", HERE / "alert_state.json"))
DEDUP_SECONDS = 30 * 60
SAMPLE = {"text": "Monitoring check: the quick brown fox jumps over the lazy dog near the river.", "max_words": 10}


def check_health(client: httpx.Client) -> None:
    resp = client.get("/health")
    if resp.status_code != 200:
        raise AssertionError(f"HTTP {resp.status_code}")
    if resp.json().get("status") != "ok":
        raise AssertionError(f"unexpected health body: {resp.text[:200]}")


def check_summarize(client: httpx.Client) -> None:
    resp = client.post("/v1/summarize", json=SAMPLE, headers={"X-API-Key": os.getenv("MONITOR_API_KEY", "")})
    if resp.status_code != 200:
        code = ""
        try:
            code = resp.json()["error"]["code"]
        except Exception:
            pass
        raise AssertionError(f"HTTP {resp.status_code} {code}".strip())
    body = SummarizeResponse.model_validate(resp.json())  # contract: raises if fields missing/wrong
    if not body.summary.strip():
        raise AssertionError("empty summary")
    if len(body.summary.split()) > SAMPLE["max_words"]:
        raise AssertionError("summary longer than max_words")


CHECKS = {"health": check_health, "summarize": check_summarize}


def run_check(name: str, fn, client: httpx.Client) -> dict:
    start = time.perf_counter()
    error = None
    try:
        fn(client)
    except (AssertionError, httpx.HTTPError, ValueError) as exc:  # ValueError covers pydantic + bad JSON
        error = f"{type(exc).__name__}: {exc}" if not isinstance(exc, AssertionError) else str(exc)
    latency_ms = int((time.perf_counter() - start) * 1000)
    if error is None and latency_ms > int(os.getenv("MAX_LATENCY_MS", "5000")):
        error = f"too slow: {latency_ms}ms"
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "check": name,
        "status": "fail" if error else "ok",
        "latency_ms": latency_ms,
        "error": error,
    }


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def should_alert(state: dict, name: str, now: float) -> bool:
    return now - state.get(name, 0) >= DEDUP_SECONDS


def main() -> int:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    state = load_state()
    failed = False
    with httpx.Client(base_url=base_url, timeout=15) as client:
        for name, fn in CHECKS.items():
            result = run_check(name, fn, client)
            print(f"{result['status'].upper():4} {name} ({result['latency_ms']}ms) {result['error'] or ''}")
            if result["status"] == "ok":
                state.pop(name, None)  # recovered: a future failure alerts again
                continue
            failed = True
            with FAILURES_FILE.open("a") as f:
                f.write(json.dumps(result) + "\n")
            now = time.time()
            if should_alert(state, name, now):
                msg = f"[ai-api-monitor] {name} check FAILED at {base_url}: {result['error']} (latency {result['latency_ms']}ms)"
                if send_alert(msg):
                    state[name] = now
            else:
                print(f"     alert for '{name}' suppressed (already alerted in the last 30 min)")
    STATE_FILE.write_text(json.dumps(state))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
