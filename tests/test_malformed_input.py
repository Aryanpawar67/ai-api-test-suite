import pytest

from .conftest import assert_error


def post_raw(client, headers, content, content_type="application/json"):
    return client.post("/v1/summarize", content=content, headers={**headers, "Content-Type": content_type})


@pytest.mark.parametrize("content", ['{"text": "hi", ', "not json", "{'text': 'x'}", "[1, 2"])
def test_invalid_json(client, headers, content):
    assert_error(post_raw(client, headers, content), 422, "validation_error")


def test_empty_body(client, headers):
    assert_error(post_raw(client, headers, ""), 422, "validation_error")


@pytest.mark.parametrize("content", ["[]", "null", '"a string"', "42"])
def test_json_but_not_an_object(client, headers, content):
    assert_error(post_raw(client, headers, content), 422, "validation_error")


def test_wrong_content_type(client, headers):
    resp = post_raw(client, headers, '{"text": "hello", "max_words": 10}', "text/plain")
    assert resp.status_code == 422


def test_invalid_utf8_bytes(client, headers):
    resp = post_raw(client, headers, b'{"text": "\xff\xfe", "max_words": 10}')
    assert resp.status_code in (400, 422)  # rejected, never a 500


@pytest.mark.parametrize(
    "text",
    ["héllo wörld ñandú", "日本語のテキストです。これは要約のテストです。", "नमस्ते दुनिया यह एक परीक्षण है", "emoji 😀🎉 text", "مرحبا بالعالم"],
)
def test_unicode_text_round_trips(client, headers, text):
    resp = client.post("/v1/summarize", json={"text": text, "max_words": 50}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["summary"]


def test_max_length_text_of_many_words(client, headers):
    text = ("word " * 1000)[:5000]
    resp = client.post("/v1/summarize", json={"text": text, "max_words": 200}, headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["summary"].split()) <= 200


def test_very_long_string_rejected(client, headers):
    resp = client.post("/v1/summarize", json={"text": "x" * 1_000_000, "max_words": 10}, headers=headers)
    assert_error(resp, 422, "validation_error")


def test_null_bytes_do_not_crash(client, headers):
    resp = client.post("/v1/summarize", json={"text": "hello\u0000world again", "max_words": 10}, headers=headers)
    assert resp.status_code in (200, 422)


def test_whitespace_only_text_is_handled(client, headers):
    resp = client.post("/v1/summarize", json={"text": "   \n\t  ", "max_words": 10}, headers=headers)
    assert resp.status_code != 500
    if resp.status_code != 200:
        assert resp.json()["error"]["code"]
