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
