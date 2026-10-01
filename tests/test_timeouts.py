import time

import pytest

from .conftest import assert_error


@pytest.mark.parametrize("fault", ["slow", "timeout"])
def test_slow_upstream_returns_504_within_limit(client, headers, payload, monkeypatch, fault):
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "0.5")
    start = time.perf_counter()
    resp = client.post("/v1/summarize", json=payload, headers={**headers, "X-Fault": fault})
    elapsed = time.perf_counter() - start
    assert_error(resp, 504, "upstream_timeout")
    assert elapsed < 2.0  # limit is 0.5s; generous slack for CI


def test_slow_fault_succeeds_if_limit_is_above_delay(client, headers, payload, monkeypatch):
    monkeypatch.setenv("SLOW_FAULT_SECONDS", "0.2")
    resp = client.post("/v1/summarize", json=payload, headers={**headers, "X-Fault": "slow"})
    assert resp.status_code == 200


def test_fault_header_ignored_when_disabled(client, headers, payload, monkeypatch):
    monkeypatch.setenv("ENABLE_FAULTS", "false")
    resp = client.post("/v1/summarize", json=payload, headers={**headers, "X-Fault": "upstream_500"})
    assert resp.status_code == 200


def test_unknown_fault_rejected(client, headers, payload):
    resp = client.post("/v1/summarize", json=payload, headers={**headers, "X-Fault": "bogus"})
    assert_error(resp, 400, "invalid_fault")
