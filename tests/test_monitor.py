import json

import httpx
import pytest

from monitor import run_checks


def make_client(handler):
    return httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))


GOOD = {"summary": "hello world", "model": "m", "latency_ms": 1, "request_id": "r"}


def handler_ok(request):
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok", "mode": "mock"})
    return httpx.Response(200, json=GOOD)


def test_checks_pass_against_healthy_api():
    with make_client(handler_ok) as c:
        assert all(run_checks.run_check(n, fn, c)["status"] == "ok" for n, fn in run_checks.CHECKS.items())


@pytest.mark.parametrize(
    "body",
    [{"summary": "x"}, {**GOOD, "summary": ""}, {**GOOD, "summary": "word " * 20}],
    ids=["missing-fields", "empty-summary", "too-long"],
)
def test_contract_violation_fails_summarize_check(body):
    with make_client(lambda r: httpx.Response(200, json=body)) as c:
        result = run_checks.run_check("summarize", run_checks.check_summarize, c)
    assert result["status"] == "fail"


def test_http_error_is_reported_with_code():
    err = {"error": {"code": "invalid_api_key", "message": "m", "request_id": "r"}}
    with make_client(lambda r: httpx.Response(403, json=err)) as c:
        result = run_checks.run_check("summarize", run_checks.check_summarize, c)
    assert result["status"] == "fail" and "403 invalid_api_key" in result["error"]


def test_connection_failure_is_a_failed_check_not_a_crash():
    def boom(request):
        raise httpx.ConnectError("refused")

    with make_client(boom) as c:
        assert run_checks.run_check("health", run_checks.check_health, c)["status"] == "fail"


def test_slow_response_fails(monkeypatch):
    monkeypatch.setenv("MAX_LATENCY_MS", "-1")
    with make_client(handler_ok) as c:
        result = run_checks.run_check("health", run_checks.check_health, c)
    assert result["status"] == "fail" and "too slow" in result["error"]


def test_dedup_window():
    t = 1_800_000_000.0
    state = {"summarize": t}
    assert not run_checks.should_alert(state, "summarize", t + 29 * 60)
    assert run_checks.should_alert(state, "summarize", t + 30 * 60)
    assert run_checks.should_alert(state, "health", t)  # never alerted before


def test_main_alerts_once_then_suppresses(tmp_path, monkeypatch):
    monkeypatch.setattr(run_checks, "FAILURES_FILE", tmp_path / "f.jsonl")
    monkeypatch.setattr(run_checks, "STATE_FILE", tmp_path / "s.json")
    sent = []
    monkeypatch.setattr(run_checks, "send_alert", lambda msg: sent.append(msg) or True)
    real_client = httpx.Client
    monkeypatch.setattr(
        run_checks.httpx, "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(lambda r: httpx.Response(500, json={})), **kw),
    )
    assert run_checks.main() == 1
    assert run_checks.main() == 1
    assert len(sent) == 2  # health and summarize each alert once; second run is suppressed
    assert len((tmp_path / "f.jsonl").read_text().splitlines()) == 4  # every failure is still logged
    assert {json.loads(l)["check"] for l in (tmp_path / "f.jsonl").read_text().splitlines()} == {"health", "summarize"}
