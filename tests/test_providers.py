import json

import pytest


def test_stream_fallback_only_before_output():
    from lms_hermes_bridge import providers

    calls = []

    def open_stream(route):
        calls.append(route)
        if route == "local":
            raise providers.ChatError("offline")
        yield route

    assert list(providers.stream_with_fallback(["local", "lan", "wan"], open_stream)) == ["lan"]
    assert calls == ["local", "lan"]

    def broken_connection(route):
        if route == "local":
            raise ConnectionResetError("connection reset")
        yield route

    assert list(providers.stream_with_fallback(["local", "lan"], broken_connection)) == ["lan"]

    def partial_stream(route):
        calls.append(route)
        yield "partial"
        raise providers.ChatError("interrupted")

    import pytest
    calls.clear()
    with pytest.raises(providers.ChatError, match="interrupted"):
        list(providers.stream_with_fallback(["local", "lan"], partial_stream))
    assert calls == ["local"]


from lms_hermes_bridge.providers import _anthropic_messages


def test_openai_image_data_url_converts_to_anthropic_base64_block():
    messages = [
        {"role": "user", "content": [
            {"type": "text", "text": "Describe this"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,cG5n"}},
        ]},
    ]
    converted = _anthropic_messages(messages)
    assert converted[0]["content"] == [
        {"type": "text", "text": "Describe this"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "cG5n"}},
    ]


def test_plain_text_messages_are_unchanged():
    messages = [{"role": "user", "content": "Hello"}]
    assert _anthropic_messages(messages) == messages


def _fake_open(events):
    """A stand-in for urlopen: yields the SSE lines a chat server would send."""
    lines = [b"data: " + json.dumps(ev).encode() + b"\n\n" for ev in events]
    lines.append(b"data: [DONE]\n\n")

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def __iter__(self):
            return iter(lines)

    return lambda req: Resp()


def test_openai_stream_reports_a_thinking_model_that_never_answered(monkeypatch):
    """max_tokens covers the reasoning channel as well, so a weak quantization can spend the whole
    budget thinking and return nothing. An empty reply looks like a dead endpoint; it is a live one
    with the wrong budget, and the chain needs that difference to fail over with a reason."""
    from lms_hermes_bridge import providers

    monkeypatch.setattr(providers, "_open", _fake_open([
        {"choices": [{"delta": {"role": "assistant", "content": ""}}]},
        {"choices": [{"delta": {"reasoning_content": "Denke"}}]},
        {"choices": [{"delta": {"reasoning_content": "nach"}}]},
        {"choices": [{"delta": {}, "finish_reason": "length"}]},
    ]))
    with pytest.raises(providers.ChatError, match="no answer"):
        list(providers.stream_openai("http://x/v1/chat/completions", "", "small-model", [],
                                     {"max_tokens": 512}))


def test_openai_stream_keeps_reasoning_out_of_the_answer(monkeypatch):
    from lms_hermes_bridge import providers

    monkeypatch.setattr(providers, "_open", _fake_open([
        {"choices": [{"delta": {"reasoning_content": "Denke nach"}}]},
        {"choices": [{"delta": {"content": "Bereit"}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]))
    out = list(providers.stream_openai("http://x/v1/chat/completions", "", "model", [],
                                       {"max_tokens": 512}))
    assert out == ["Bereit"]


def test_openai_stream_tolerates_a_budget_cut_answer(monkeypatch):
    """A model that answered and then ran out of budget is a partial answer, not a missing one."""
    from lms_hermes_bridge import providers

    monkeypatch.setattr(providers, "_open", _fake_open([
        {"choices": [{"delta": {"reasoning_content": "Denke nach"}}]},
        {"choices": [{"delta": {"content": "Halb"}}]},
        {"choices": [{"delta": {}, "finish_reason": "length"}]},
    ]))
    out = list(providers.stream_openai("http://x/v1/chat/completions", "", "model", [],
                                       {"max_tokens": 512}))
    assert out == ["Halb"]
