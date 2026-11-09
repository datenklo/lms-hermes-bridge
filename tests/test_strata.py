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