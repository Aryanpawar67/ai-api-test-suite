import pytest

from .conftest import assert_error


def test_missing_key_returns_401(client, payload):
    assert_error(client.post("/v1/summarize", json=payload), 401, "missing_api_key")


@pytest.mark.parametrize("key", ["wrong", " ", "test-key-1x", "TEST-KEY-1"])
def test_wrong_key_returns_403(client, payload, key):
    resp = client.post("/v1/summarize", json=payload, headers={"X-API-Key": key})
    assert_error(resp, 403, "invalid_api_key")


@pytest.mark.parametrize("key", ["test-key-1", "test-key-2"])
def test_valid_key_returns_200(client, payload, key):
    resp = client.post("/v1/summarize", json=payload, headers={"X-API-Key": key})
    assert resp.status_code == 200


def test_auth_checked_before_validation(client):
    resp = client.post("/v1/summarize", json={"bad": "body"})
    assert resp.status_code == 401


def test_health_needs_no_key(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "mode": "mock"}


def test_repeated_invalid_keys_get_throttled(client, payload, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    codes = [
        client.post("/v1/summarize", json=payload, headers={"X-API-Key": f"bad{i}"}).status_code
        for i in range(5)
    ]
    assert codes == [403, 403, 403, 429, 429]
    # A valid key is not locked out by someone else's failed guesses.
    ok = client.post("/v1/summarize", json=payload, headers={"X-API-Key": "test-key-1"})
    assert ok.status_code == 200
