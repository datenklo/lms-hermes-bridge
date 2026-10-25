"""Streaming chat clients for OpenAI-compatible and Anthropic endpoints (stdlib only)."""
import json
import re
import urllib.error
import urllib.request
from typing import Iterator


class ChatError(Exception):
    pass


def _open(req: urllib.request.Request, timeout: float = 120):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise ChatError(f"HTTP {e.code}: {body}") from e
    except OSError as e:
        raise ChatError(str(e)) from e


def _sse(resp) -> Iterator[dict]:
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            yield json.loads(data)
        except ValueError:
            continue


def _anthropic_messages(messages: list) -> list:
    """Translate OpenAI image_url data blocks to Anthropic base64 source blocks."""
    out = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            out.append(message)
            continue
        blocks = []
        for block in content:
            if block.get("type") != "image_url":
                blocks.append(block)
                continue
            url = block.get("image_url", {}).get("url", "")
            match = re.fullmatch(r"data:(image/[a-zA-Z0-9.+-]+);base64,(.+)", url, re.S)
            if match:
                blocks.append({"type": "image", "source": {
                    "type": "base64", "media_type": match.group(1), "data": match.group(2)}})
        out.append({**message, "content": blocks})
    return out


def stream_openai(endpoint: str, api_key: str, model: str, messages: list, params: dict) -> Iterator[str]:
    body = {"model": model, "messages": messages, "stream": True}
    if "temperature" in params:
        body["temperature"] = params["temperature"]
    if "max_tokens" in params:
        body["max_tokens"] = params["max_tokens"]
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(endpoint, json.dumps(body).encode(), headers)
    with _open(req) as resp:
        for ev in _sse(resp):
            for choice in ev.get("choices", []):
                text = (choice.get("delta") or {}).get("content")
                if text:
                    yield text


def stream_anthropic(endpoint: str, api_key: str, model: str, messages: list, params: dict) -> Iterator[str]:
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    body = {
        "model": model,
        "max_tokens": params.get("max_tokens", 2048),
        "messages": _anthropic_messages([m for m in messages if m["role"] != "system"]),
        "stream": True,
    }
    if system:
        body["system"] = system
    if "temperature" in params:
        body["temperature"] = params["temperature"]
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    req = urllib.request.Request(endpoint, json.dumps(body).encode(), headers)
    with _open(req) as resp:
        for ev in _sse(resp):
            if ev.get("type") == "content_block_delta":
                text = ev.get("delta", {}).get("text")
                if text:
                    yield text


def stream(kind: str, endpoint: str, api_key: str, model: str, messages: list, params: dict) -> Iterator[str]:
    fn = stream_anthropic if kind == "anthropic" else stream_openai
    return fn(endpoint, api_key, model, messages, params)
