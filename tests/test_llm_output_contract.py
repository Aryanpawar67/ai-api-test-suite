"""Contract checks on LLM output: structure and constraints, never exact text.

The same checks run against the mock (always) and the real model (`-m live`).
"""
import os
import unicodedata

import pytest

from target_api import main
from target_api.llm_client import AnthropicLLMClient

from .conftest import assert_error

LEAK_MARKERS = ["you summarize text", "system prompt", "reply with only the summary"]

SAMPLES = {
    "english": ("The city council met on Tuesday to discuss the new bike lanes. Several residents spoke in favor, "
                "while shop owners worried about parking. A vote was postponed until next month.", "LATIN"),
    "japanese": ("市議会は火曜日に新しい自転車レーンについて話し合いました。多くの住民が賛成しましたが、"
                 "商店主は駐車場の不足を心配しました。採決は来月に延期されました。", "CJK"),
    "hindi": ("नगर परिषद ने मंगलवार को नई साइकिल लेन पर चर्चा की। कई निवासियों ने समर्थन किया, "
              "जबकि दुकानदारों को पार्किंग की चिंता थी। मतदान अगले महीने तक टाला गया।", "DEVANAGARI"),
}


def dominant_script(text: str) -> str:
    counts: dict[str, int] = {}
    for ch in text:
        if ch.isalpha():
            script = unicodedata.name(ch, "UNKNOWN").split()[0]
            counts[script] = counts.get(script, 0) + 1
    return max(counts, key=counts.get) if counts else "NONE"


def check_contract(resp, text, max_words, script):
    assert resp.status_code == 200, resp.text
    summary = resp.json()["summary"]
    assert summary.strip(), "summary is empty"
    # CJK has no spaces, so the word limit only applies to space-separated scripts.
    if script != "CJK":
        assert len(summary.split()) <= max_words
    assert dominant_script(summary) == script or (script == "CJK" and dominant_script(summary) in {"CJK", "HIRAGANA", "KATAKANA"})
    lowered = summary.lower()
    assert not any(marker in lowered for marker in LEAK_MARKERS), "possible prompt leak"


@pytest.mark.parametrize("name", SAMPLES)
@pytest.mark.parametrize("max_words", [10, 25, 200])
def test_summary_meets_contract(client, headers, name, max_words):
    text, script = SAMPLES[name]
    resp = client.post("/v1/summarize", json={"text": text, "max_words": max_words}, headers=headers)
    check_contract(resp, text, max_words, script)


def test_mock_is_deterministic(client, headers, payload):
    first = client.post("/v1/summarize", json=payload, headers=headers).json()["summary"]
    second = client.post("/v1/summarize", json=payload, headers=headers).json()["summary"]
    assert first == second


@pytest.mark.parametrize(
    "fault, code",
    [("bad_json", "bad_upstream_response"), ("empty_output", "empty_upstream_output"), ("upstream_500", "upstream_error")],
)
def test_bad_upstream_output_is_a_handled_error(client, headers, payload, fault, code):
    resp = client.post("/v1/summarize", json=payload, headers={**headers, "X-Fault": fault})
    assert_error(resp, 502, code)


def test_upstream_details_not_leaked_to_client(client, headers, payload):
    resp = client.post("/v1/summarize", json=payload, headers={**headers, "X-Fault": "upstream_500"})
    assert "HTTP 500" not in resp.text


@pytest.mark.live
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
@pytest.mark.parametrize("name", SAMPLES)
def test_live_summary_meets_contract(client, headers, monkeypatch, name):
    monkeypatch.setattr(main, "llm", AnthropicLLMClient())
    text, script = SAMPLES[name]
    resp = client.post("/v1/summarize", json={"text": text, "max_words": 30}, headers=headers)
    check_contract(resp, text, 30, script)
