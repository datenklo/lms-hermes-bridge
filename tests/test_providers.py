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
