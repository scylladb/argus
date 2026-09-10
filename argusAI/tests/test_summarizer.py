"""Unit tests for Summarizer: token accounting and stop-reason handling with a mocked client."""

from types import SimpleNamespace

import pytest

from argusAI.utils.summarizer import Summarizer, SummarizerError


def _response(text="short summary", stop_reason="end_turn", **usage):
    base = {"input_tokens": 500, "output_tokens": 40, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    base.update(usage)
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category="cyber") if stop_reason == "refusal" else None,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(**base),
    )


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _summarizer(response):
    s = Summarizer(api_key="test-key")
    s._client = SimpleNamespace(messages=FakeMessages(response))
    return s


def test_usage_maps_to_result():
    s = _summarizer(_response(cache_read_input_tokens=1200, cache_creation_input_tokens=300))
    res = s.summarize("claude-sonnet-5", "event body", output_config={"effort": "low"})
    assert res.summary == "short summary"
    assert (res.prompt_tokens, res.cached_tokens, res.cache_write_tokens, res.completion_tokens) == (
        2000,
        1200,
        300,
        40,
    )
    call = s._client.messages.calls[0]
    assert call["output_config"] == {"effort": "low"}
    assert call["max_tokens"] == 16000
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_refusal_raises():
    with pytest.raises(SummarizerError, match="refused"):
        _summarizer(_response(stop_reason="refusal")).summarize("claude-sonnet-5", "event body")


def test_truncation_raises():
    with pytest.raises(SummarizerError, match="max_tokens"):
        _summarizer(_response(stop_reason="max_tokens")).summarize("claude-sonnet-5", "event body")


def test_raw_completion_returns_text_only():
    assert (
        _summarizer(_response(text='{"coverage": 90}')).raw_completion("claude-opus-5", "sys", "user")
        == '{"coverage": 90}'
    )
