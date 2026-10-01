import pytest

from target_api.schemas import ErrorResponse, SummarizeResponse

from .conftest import assert_error


def test_valid_payload_matches_response_schema(client, headers, payload):
    resp = client.post("/v1/summarize", json=payload, headers=headers)
    assert resp.status_code == 200
    body = SummarizeResponse.model_validate(resp.json())
    assert body.request_id == resp.headers["X-Request-ID"]
    assert body.latency_ms >= 0


@pytest.mark.parametrize("missing", ["text", "max_words"])
def test_missing_field(client, headers, payload, missing):
    del payload[missing]
    assert_error(client.post("/v1/summarize", json=payload, headers=headers), 422, "validation_error")


@pytest.mark.parametrize(
    "body",
    [
        {"text": 123, "max_words": 10},
        {"text": ["a"], "max_words": 10},
        {"text": "hello", "max_words": "ten"},
        {"text": "hello", "max_words": 10.5},
        {"text": None, "max_words": 10},
    ],
)
def test_wrong_types(client, headers, body):
    assert_error(client.post("/v1/summarize", json=body, headers=headers), 422, "validation_error")


def test_text_too_long(client, headers):
    resp = client.post("/v1/summarize", json={"text": "a" * 5001, "max_words": 10}, headers=headers)
    assert_error(resp, 422, "validation_error")


@pytest.mark.parametrize("text", ["a", "a" * 5000])
def test_text_length_boundaries_accepted(client, headers, text):
    resp = client.post("/v1/summarize", json={"text": text, "max_words": 10}, headers=headers)
    assert resp.status_code == 200


def test_empty_text_rejected(client, headers):
    resp = client.post("/v1/summarize", json={"text": "", "max_words": 10}, headers=headers)
    assert_error(resp, 422, "validation_error")


@pytest.mark.parametrize("max_words", [-1, 0, 9, 201, 10_000])
def test_max_words_out_of_range(client, headers, max_words):
    resp = client.post("/v1/summarize", json={"text": "hello world", "max_words": max_words}, headers=headers)
    assert_error(resp, 422, "validation_error")


@pytest.mark.parametrize("max_words", [10, 200])
def test_max_words_boundaries_accepted(client, headers, max_words):
    resp = client.post("/v1/summarize", json={"text": "hello world", "max_words": max_words}, headers=headers)
    assert resp.status_code == 200


def test_error_body_matches_error_schema(client, headers):
    resp = client.post("/v1/summarize", json={}, headers=headers)
    ErrorResponse.model_validate(resp.json())
