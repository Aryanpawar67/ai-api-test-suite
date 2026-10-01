import time

import pytest

from target_api import main

from .conftest import assert_error


@pytest.fixture
def limited(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")


def test_burst_above_limit_returns_429_with_retry_after(client, headers, payload, limited):
    codes = [client.post("/v1/summarize", json=payload, headers=headers).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    resp = client.post("/v1/summarize", json=payload, headers=headers)
    assert_error(resp, 429, "rate_limited")
    assert int(resp.headers["Retry-After"]) >= 1


def test_limit_is_per_key(client, payload, limited):
    for _ in range(3):
        client.post("/v1/summarize", json=payload, headers={"X-API-Key": "test-key-1"})
    blocked = client.post("/v1/summarize", json=payload, headers={"X-API-Key": "test-key-1"})
    other = client.post("/v1/summarize", json=payload, headers={"X-API-Key": "test-key-2"})
    assert (blocked.status_code, other.status_code) == (429, 200)


def test_health_is_not_rate_limited(client, limited):
    assert all(client.get("/health").status_code == 200 for _ in range(10))


def test_recovers_after_window(client, headers, payload, limited, monkeypatch):
    monkeypatch.setattr(main, "RATE_WINDOW_SECONDS", 1)
    for _ in range(3):
        client.post("/v1/summarize", json=payload, headers=headers)
    assert client.post("/v1/summarize", json=payload, headers=headers).status_code == 429
    time.sleep(1.1)
    assert client.post("/v1/summarize", json=payload, headers=headers).status_code == 200
