"""Run the Pi coding agent in JSON mode and stream assistant text."""
import json
import os
import queue
import signal
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import router
from .providers import ChatError, RetryUnsafeError


def priority_routes(cfg, prompt, model_lists, mem_bytes):
    pi = cfg["pi"]
    providers = list(cfg["providers"])
    if pi.get("base_url") and pi.get("model"):
        providers.insert(0, {"id": "__pi_endpoint__", "kind": "openai", "model": pi["model"],
                             "endpoint": pi["base_url"].rstrip("/") + "/chat/completions",
                             "api_key": pi.get("api_key", "")})
    return router.priority_routes(prompt, {**cfg, "providers": providers}, model_lists, mem_bytes)


def route_config(cfg, route):
    if route.backend == "provider":
        if route.provider_id == "__pi_endpoint__":
            return dict(cfg["pi"])
        provider = next(provider for provider in cfg["providers"] if provider["id"] == route.provider_id)
        endpoint = urlsplit(provider["endpoint"])
        suffix = "/v1/messages" if provider["kind"] == "anthropic" else "/chat/completions"
        if not endpoint.path.rstrip("/").endswith(suffix) or endpoint.query or endpoint.fragment:
            raise ChatError("Pi provider endpoint must end in " + suffix)
        base_url = urlunsplit((endpoint.scheme, endpoint.netloc, endpoint.path.rstrip("/")[:-len(suffix)], "", ""))
        return {**cfg["pi"], "base_url": base_url, "model": route.model,
                "api_key": provider.get("api_key", ""),
                "api": "anthropic-messages" if provider["kind"] == "anthropic" else "openai-completions"}
    settings = cfg[route.backend]
    return {**cfg["pi"], "base_url": settings["url"].rstrip("/") + "/v1", "model": route.model,
            "api_key": settings.get("api_key", ""), "api": "openai-completions"}


def command(cfg: dict, system_prompt: str) -> list[str]:
    executable = cfg.get("executable") or "pi"
    args = [os.path.expanduser(executable), "--mode", "json", "--no-session", "--no-approve"]
    if cfg.get("safe_fallback"):
        args += ["--no-extensions", "--no-mcp"]
    if cfg.get("model"):
        args += ["--model", cfg["model"]]
    if cfg.get("model") and (cfg.get("provider") or cfg.get("base_url")):
        args += ["--provider", "lms-bridge" if cfg.get("base_url") else cfg["provider"]]
    if system_prompt.strip():
        args += ["--append-system-prompt", system_prompt]
    return args


def stream(cfg: dict, prompt: str, system_prompt: str, cancel: threading.Event):
    agent_dir = None
    try:
        environment = os.environ.copy()
        if cfg.get("base_url"):
            if not cfg.get("model"):
                raise ChatError("Pi requires a model for the configured API endpoint")
            agent_dir = tempfile.TemporaryDirectory(prefix="lms-bridge-pi-")
            environment["PI_CODING_AGENT_DIR"] = agent_dir.name
            environment["LMS_BRIDGE_PI_API_KEY"] = cfg.get("api_key") or "local"
            models = {"providers": {"lms-bridge": {"baseUrl": cfg["base_url"], "api": cfg.get("api", "openai-completions"),
                      "apiKey": "$LMS_BRIDGE_PI_API_KEY", "models": [{"id": cfg["model"]}]}}}
            (Path(agent_dir.name) / "models.json").write_text(json.dumps(models), encoding="utf-8")
        process = subprocess.Popen(command(cfg, system_prompt), cwd=str(Path(cfg.get("working_directory") or "~").expanduser()),
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace", start_new_session=True, env=environment)
    except OSError as error:
        if agent_dir:
            agent_dir.cleanup()
        raise ChatError(str(error)) from error

    lines = queue.Queue()

    def read_stream(source, stream):
        try:
            for line in stream:
                lines.put((source, line))
        finally:
            lines.put((source, None))

    for source, output in (("stdout", process.stdout), ("stderr", process.stderr)):
        threading.Thread(target=read_stream, args=(source, output), daemon=True).start()
    try:
        try:
            process.stdin.write(prompt)
            process.stdin.close()
        except OSError:
            pass
        remaining = 2
        errors = []
        event_error = ""
        tool_started = False
        while remaining and not cancel.is_set():
            try:
                source, line = lines.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                remaining -= 1
                continue
            if source == "stderr":
                errors.append(line[:1000])
                errors = errors[-10:]
                continue
            try:
                event = json.loads(line)
            except ValueError:
                tool_started = True
                continue
            if not isinstance(event, dict):
                tool_started = True
                continue
            if event.get("type") in ("tool_execution_start", "tool_execution_update", "tool_execution_end"):
                tool_started = True
            elif event.get("type") == "message_update":
                update = event.get("assistantMessageEvent") or {}
                if update.get("type") in ("toolcall_start", "toolcall_delta", "toolcall_end"):
                    tool_started = True
                if update.get("type") == "text_delta" and update.get("delta"):
                    event_error = ""
                    yield update["delta"]
            elif event.get("type") == "message_end":
                message = event.get("message") or {}
                if message.get("role") == "assistant" and message.get("stopReason") in ("error", "aborted"):
                    event_error = message.get("errorMessage") or "Pi reported an error or aborted"
            elif event.get("type") == "auto_retry_end" and not event.get("success"):
                event_error = event.get("finalError") or event_error
        if not cancel.is_set():
            code = process.wait()
            if code or event_error:
                error = event_error or "".join(errors).strip() or f"Pi exited with code {code}"
                raise (RetryUnsafeError if tool_started or (code and not event_error) else ChatError)(error)
    finally:
        if process.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait()
        if agent_dir:
            agent_dir.cleanup()