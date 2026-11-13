import io

from lms_hermes_bridge import strata


def test_list_models_uses_openai_endpoint_and_key(monkeypatch):
    requests = []

    def open_request(request, timeout):
        requests.append(request)
        return io.BytesIO(b'{"data":[{"id":"qwen-35b"}]}')

    monkeypatch.setattr(strata.urllib.request, "urlopen", open_request)
    models = strata.list_models({"url": "http://127.0.0.1:8080/", "api_key": "secret", "vision": True})
    assert requests[0].full_url == "http://127.0.0.1:8080/v1/models"
    assert requests[0].get_header("Authorization") == "Bearer secret"
    assert models[0].loaded and models[0].supports_vision and models[0].params_b == 35


def test_invalid_server_url_is_unavailable():
    assert strata.list_models({"url": "invalid"}) is None


def test_list_models_reads_status_context_and_modalities(monkeypatch):
    """A llama.cpp-style server says what it can do; the bridge must not guess."""
    import io
    import json

    payload = {"data": [
        {"id": "qwen3-vl-30b", "status": {"value": "loaded"}, "meta": {"n_ctx": 131072},
         "architecture": {"input_modalities": ["text", "image"]}},
        {"id": "small-8b", "status": {"value": "not_loaded"}, "meta": {"n_ctx": 8192}},
    ]}
    monkeypatch.setattr(strata.urllib.request, "urlopen",
                        lambda request, timeout: io.BytesIO(json.dumps(payload).encode()))
    models = strata.list_models({"url": "http://127.0.0.1:8080", "vision": False})
    assert models[0].loaded and models[0].supports_vision and models[0].max_context == 131072
    assert not models[1].loaded and not models[1].supports_vision and models[1].max_context == 8192
