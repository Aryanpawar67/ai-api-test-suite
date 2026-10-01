"""LLM clients: a deterministic mock and a live Anthropic client.

Both expose `async summarize(text, max_words) -> (summary, model)`.
`get_client()` picks one based on the MOCK_LLM env var.
"""
import asyncio
import json
import os
from typing import Protocol

from .faults import slow_fault_seconds


class UpstreamError(Exception):
    """The LLM provider failed or returned something unusable."""

    code = "upstream_error"


class BadUpstreamResponse(UpstreamError):
    code = "bad_upstream_response"


class EmptyUpstreamOutput(UpstreamError):
    code = "empty_upstream_output"


class LLMClient(Protocol):
    mode: str

    async def summarize(
        self, text: str, max_words: int, fault: str | None = None
    ) -> tuple[str, str]: ...


class MockLLMClient:
    mode = "mock"
    model = "mock-summarizer-1"

    async def summarize(
        self, text: str, max_words: int, fault: str | None = None
    ) -> tuple[str, str]:
        if fault == "timeout":
            await asyncio.sleep(3600)  # hangs; the API's timeout cancels it
        if fault == "slow":
            await asyncio.sleep(slow_fault_seconds())  # finite, but longer than the limit
        if fault == "upstream_500":
            raise UpstreamError("mock upstream returned HTTP 500")

        # Simulate the provider's raw reply, then parse it like a real client would.
        # Deterministic: the first max_words words of the input.
        summary = " ".join(text.split()[:max_words])
        if fault == "bad_json":
            raw = '{"summary": "truncated reply'
        elif fault == "empty_output":
            raw = json.dumps({"summary": ""})
        else:
            raw = json.dumps({"summary": summary})
        try:
            return json.loads(raw)["summary"], self.model
        except (json.JSONDecodeError, KeyError) as exc:
            raise BadUpstreamResponse(f"unparseable upstream reply: {exc}") from exc


class AnthropicLLMClient:
    mode = "live"

    def __init__(self) -> None:
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when MOCK_LLM=false")
        self._anthropic = anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    async def summarize(
        self, text: str, max_words: int, fault: str | None = None
    ) -> tuple[str, str]:
        # Faults are mock-only; ignored here.
        try:
            resp = await self._client.messages.create(
                model=self.model,
                max_tokens=max_words * 4,
                system=(
                    "You summarize text. Reply with only the summary, in the same "
                    f"language as the input, in at most {max_words} words."
                ),
                messages=[{"role": "user", "content": text}],
            )
        except self._anthropic.APIError as exc:
            raise UpstreamError(f"upstream error: {exc}") from exc
        summary = "".join(b.text for b in resp.content if b.type == "text").strip()
        return summary, self.model


def mock_enabled() -> bool:
    return os.getenv("MOCK_LLM", "true").lower() == "true"


def get_client() -> LLMClient:
    return MockLLMClient() if mock_enabled() else AnthropicLLMClient()
