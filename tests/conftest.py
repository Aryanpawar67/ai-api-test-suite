import os

# Must be set before target_api.main is imported (the LLM client is chosen at import).
os.environ["MOCK_LLM"] = "true"

import pytest
from fastapi.testclient import TestClient

from target_api import main

TEST_KEY = "test-key-1"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("API_KEYS", f"{TEST_KEY},test-key-2")
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("ENABLE_FAULTS", "true")
    main.reset_rate_limiter()
    yield
    main.reset_rate_limiter()


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def headers():
    return {"X-API-Key": TEST_KEY}


@pytest.fixture
def payload():
    return {"text": "The quick brown fox jumps over the lazy dog near the river bank.", "max_words": 10}


def assert_error(resp, status, code):
    """Every error must use the documented error schema."""
    assert resp.status_code == status, resp.text
    err = resp.json()["error"]
    assert err["code"] == code
    assert err["message"]
    assert err["request_id"]
