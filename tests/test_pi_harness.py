import io
import json
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lms_hermes_bridge import pi_harness
from lms_hermes_bridge.providers import ChatError


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


def test_pi_abort_event_is_reported(monkeypatch, tmp_path):
    process = FakeProcess('{"type":"message_end","message":{"role":"assistant","stopReason":"aborted"}}\n')
    monkeypatch.setattr(pi_harness.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(ChatError, match="aborted"):
        list(pi_harness.stream({"working_directory": str(tmp_path)}, "hello", "", threading.Event()))


def test_executable_expands_user_directory():
    assert pi_harness.command({"executable": "~/bin/pi"}, "")[0] == os.path.expanduser("~/bin/pi")


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
        content = next(message["content"] for message in requests[0]["messages"] if message["role"] == "user")
        assert content == "bridge test prompt" or any(block.get("text") == "bridge test prompt" for block in content)
    finally:
        server.shutdown()
        server.server_close()