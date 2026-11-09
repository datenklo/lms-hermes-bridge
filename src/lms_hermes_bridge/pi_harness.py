"""Run the Pi coding agent in JSON mode and stream assistant text."""
import json
import os
import queue
import signal
import subprocess
import threading
from pathlib import Path

from .providers import ChatError


def command(cfg: dict, system_prompt: str) -> list[str]:
    executable = cfg.get("executable") or "pi"
    args = [os.path.expanduser(executable), "--mode", "json", "--no-session", "--no-approve"]
    if cfg.get("model"):
        args += ["--model", cfg["model"]]
    if cfg.get("provider") and cfg.get("model"):
        args += ["--provider", cfg["provider"]]
    if system_prompt.strip():
        args += ["--append-system-prompt", system_prompt]
    return args


def stream(cfg: dict, prompt: str, system_prompt: str, cancel: threading.Event):
    try:
        process = subprocess.Popen(command(cfg, system_prompt), cwd=str(Path(cfg.get("working_directory") or "~").expanduser()),
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace", start_new_session=True)
    except OSError as error:
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
                continue
            if event.get("type") == "message_update":
                update = event.get("assistantMessageEvent") or {}
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
                raise ChatError(event_error or "".join(errors).strip() or f"Pi exited with code {code}")
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