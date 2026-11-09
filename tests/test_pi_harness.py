import io
import json
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

from lms_hermes_bridge import pi_harness
from lms_hermes_bridge.config import DEFAULTS
from lms_hermes_bridge.lmstudio import ModelInfo
from lms_hermes_bridge.providers import ChatError, RetryUnsafeError, stream_with_fallback
import copy


class FakeProcess:
    def __init__(self, stdout, stderr="", code=0):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self.code = code
        self.pid = 123

    def wait(self, timeout=None):
        return self.code

    def poll(self):
        return self.code


def test_pi_json_stream_and_argument_safety(monkeypatch, tmp_path):
    process = FakeProcess('{"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"Hello"}}\n')
    calls = []
    monkeypatch.setattr(pi_harness.subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs)) or process)
    cfg = {"executable": "pi", "provider": "strata", "model": "model", "working_directory": str(tmp_path)}
    assert list(pi_harness.stream(cfg, "-unsafe prompt", "instructions", threading.Event())) == ["Hello"]
    args, kwargs = calls[0]
    assert args[:4] == ["pi", "--mode", "json", "--no-session"]
    assert "-unsafe prompt" not in args and kwargs["cwd"] == str(tmp_path)
    assert args[args.index("--provider") + 1] == "strata"


def test_pi_error_event_is_reported(monkeypatch, tmp_path):
    process = FakeProcess('{"type":"message_end","message":{"role":"assistant","stopReason":"error","errorMessage":"model unavailable"}}\n')
    monkeypatch.setattr(pi_harness.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(ChatError, match="model unavailable"):
        list(pi_harness.stream({"working_directory": str(tmp_path)}, "hello", "", threading.Event()))


def test_pi_does_not_retry_after_tool_activity(monkeypatch, tmp_path):
    events = '{"type":"tool_execution_start","toolName":"bash"}\n' + (
        '{"type":"message_end","message":{"role":"assistant","stopReason":"error",'
        '"errorMessage":"model unavailable"}}\n')
    launches = []
    monkeypatch.setattr(pi_harness.subprocess, "Popen", lambda *args, **kwargs: launches.append(1) or FakeProcess(events))
    cfg = {"working_directory": str(tmp_path)}
    with pytest.raises(RetryUnsafeError, match="model unavailable"):
        list(stream_with_fallback(["first", "second"],
                                  lambda _: pi_harness.stream(cfg, "test", "", threading.Event())))
    assert len(launches) == 1


def test_pi_unknown_process_failure_is_not_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(pi_harness.subprocess, "Popen", lambda *args, **kwargs: FakeProcess("", code=1))
    with pytest.raises(RetryUnsafeError):
        list(pi_harness.stream({"working_directory": str(tmp_path)}, "test", "", threading.Event()))
    assert "--no-extensions" in pi_harness.command({"safe_fallback": True}, "")
    assert "--no-mcp" in pi_harness.command({"safe_fallback": True}, "")


@pytest.mark.parametrize("invalid_event", ["not-json", "null", "[]"])
def test_pi_does_not_retry_after_invalid_event(monkeypatch, tmp_path, invalid_event):
    events = invalid_event + '\n{"type":"message_end","message":{"role":"assistant",' \
        '"stopReason":"error","errorMessage":"model unavailable"}}\n'
    launches = []
    monkeypatch.setattr(pi_harness.subprocess, "Popen", lambda *args, **kwargs: launches.append(1) or FakeProcess(events))
    with pytest.raises(RetryUnsafeError, match="model unavailable"):
        list(stream_with_fallback(["first", "second"],
                                  lambda _: pi_harness.stream({"working_directory": str(tmp_path)}, "test", "", threading.Event())))
    assert len(launches) == 1


def test_pi_priority_candidates_and_provider_configuration():
    cfg = copy.deepcopy(DEFAULTS)
    cfg["pi"].update(base_url="http://192.168.1.5:1234/v1", model="remote", api_key="pi-key")
    cfg["providers"] = [{"id": "cloud", "kind": "anthropic", "endpoint": "https://api.anthropic.com/v1/messages",
                         "model": "claude", "api_key": "cloud-key"}]
    routes = pi_harness.priority_routes(cfg, "open file", {"lmstudio": [ModelInfo("local", loaded=True)]}, 2**30)
    assert [route.model for route in routes] == ["local", "remote", "claude"]
    assert pi_harness.route_config(cfg, routes[0])["base_url"] == "http://localhost:1234/v1"
    assert pi_harness.route_config(cfg, routes[1])["api_key"] == "pi-key"
    cloud = pi_harness.route_config(cfg, routes[2])
    assert cloud["base_url"] == "https://api.anthropic.com" and cloud["api"] == "anthropic-messages"


def test_pi_abort_event_is_reported(monkeypatch, tmp_path):
    process = FakeProcess('{"type":"message_end","message":{"role":"assistant","stopReason":"aborted"}}\n')
    monkeypatch.setattr(pi_harness.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(ChatError, match="aborted"):
        list(pi_harness.stream({"working_directory": str(tmp_path)}, "hello", "", threading.Event()))


def test_executable_expands_user_directory():
    assert pi_harness.command({"executable": "~/bin/pi"}, "")[0] == os.path.expanduser("~/bin/pi")


def test_custom_pi_endpoint_uses_temporary_agent_configuration(monkeypatch, tmp_path):
    process = FakeProcess("")
    recorded = {}

    def launch(args, **kwargs):
        recorded.update(args=args, environment=kwargs["env"])
        recorded["models"] = json.loads((pi_harness.Path(kwargs["env"]["PI_CODING_AGENT_DIR"]) / "models.json").read_text())
        return process

    monkeypatch.setattr(pi_harness.subprocess, "Popen", launch)
    cfg = {"working_directory": str(tmp_path), "base_url": "http://192.168.1.2:1234/v1",
           "api_key": "private-key", "model": "model"}
    assert list(pi_harness.stream(cfg, "test", "", threading.Event())) == []
    assert recorded["args"][recorded["args"].index("--provider") + 1] == "lms-bridge"
    assert recorded["models"]["providers"]["lms-bridge"]["apiKey"] == "$LMS_BRIDGE_PI_API_KEY"
    assert recorded["environment"]["LMS_BRIDGE_PI_API_KEY"] == "private-key"
    assert not pi_harness.Path(recorded["environment"]["PI_CODING_AGENT_DIR"]).exists()


def test_missing_pi_executable_is_reported(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise FileNotFoundError("pi not found")
    monkeypatch.setattr(pi_harness.subprocess, "Popen", fail)
    with pytest.raises(ChatError, match="pi not found"):
        list(pi_harness.stream({"working_directory": str(tmp_path)}, "hello", "", threading.Event()))


def test_cancel_terminates_running_pi(monkeypatch, tmp_path):
    process = FakeProcess("")
    process.terminated = False
    process.poll = lambda: 0 if process.terminated else None
    process.terminate = lambda: setattr(process, "terminated", True)
    monkeypatch.setattr(pi_harness.os, "killpg", lambda *_: process.terminate(), raising=False)
    monkeypatch.setattr(pi_harness.subprocess, "Popen", lambda *args, **kwargs: process)
    cancel = threading.Event()
    cancel.set()
    assert list(pi_harness.stream({"working_directory": str(tmp_path)}, "hello", "", cancel)) == []
    assert process.terminated


@pytest.mark.skipif(not os.environ.get("LMS_BRIDGE_TEST_PI"), reason="requires an installed Pi CLI")
def test_real_pi_streams_from_local_openai_endpoint(monkeypatch, tmp_path):
    executable = shutil.which("pi")
    if not executable:
        pytest.skip("Pi CLI is not installed")
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            events = [
                {"id": "test", "object": "chat.completion.chunk", "created": 0, "model": "bridge-test",
                 "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hello from Pi"},
                              "finish_reason": None}]},
                {"id": "test", "object": "chat.completion.chunk", "created": 0, "model": "bridge-test",
                 "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ]
            body = ("".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        (tmp_path / "models.json").write_text(json.dumps({"providers": {"bridge-test": {
            "baseUrl": f"http://127.0.0.1:{server.server_port}/v1", "api": "openai-completions",
            "apiKey": "test", "models": [{"id": "bridge-test"}],
        }}}), encoding="utf-8")
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
        monkeypatch.setenv("PI_OFFLINE", "1")
        monkeypatch.setenv("PI_TELEMETRY", "0")
        cfg = {"executable": executable, "working_directory": str(tmp_path),
               "model": "bridge-test", "provider": "bridge-test"}
        assert "".join(pi_harness.stream(cfg, "bridge test prompt", "", threading.Event())) == "Hello from Pi"
        cfg.update(base_url=f"http://127.0.0.1:{server.server_port}/v1", api_key="test")
        assert "".join(pi_harness.stream(cfg, "second prompt", "", threading.Event())) == "Hello from Pi"
        content = next(message["content"] for message in requests[0]["messages"] if message["role"] == "user")
        assert content == "bridge test prompt" or any(block.get("text") == "bridge test prompt" for block in content)
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(not os.environ.get("LMS_BRIDGE_TEST_PI"), reason="requires an installed Pi CLI")
def test_real_pi_anthropic_endpoint_path_and_key(monkeypatch, tmp_path):
    executable = shutil.which("pi")
    if not executable:
        pytest.skip("Pi CLI is not installed")
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append((self.path, self.headers.get("x-api-key")))
            self.rfile.read(int(self.headers["Content-Length"]))
            events = [
                ("message_start", {"type": "message_start", "message": {"id": "test", "type": "message",
                   "role": "assistant", "model": "claude-test", "content": [], "usage": {"input_tokens": 1, "output_tokens": 0}}}),
                ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
                ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}),
                ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 1}}),
                ("message_stop", {"type": "message_stop"}),
            ]
            body = "".join(f"event: {name}\ndata: {json.dumps(event)}\n\n" for name, event in events).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("PI_OFFLINE", "1")
    try:
        cfg = copy.deepcopy(DEFAULTS)
        cfg["pi"].update(executable=executable, working_directory=str(tmp_path))
        cfg["providers"] = [{"id": "anthropic", "kind": "anthropic", "model": "claude-test", "api_key": "test-key",
                             "endpoint": f"http://127.0.0.1:{server.server_port}/v1/messages"}]
        route = pi_harness.priority_routes(cfg, "open file", {}, 0)[0]
        pi_cfg = {**pi_harness.route_config(cfg, route), "safe_fallback": True}
        assert "".join(pi_harness.stream(pi_cfg, "hello", "", threading.Event())) == "Hello"
        assert len(requests) == 1 and urlsplit(requests[0][0]).path == "/v1/messages"
        assert requests[0][1] == "test-key"
    finally:
        server.shutdown()
        server.server_close()