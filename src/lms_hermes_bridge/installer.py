"""Detects missing LM Studio / Hermes installs and runs their official install scripts."""
import re
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlparse

from . import lmstudio

NAMES = {"lmstudio": "LM Studio", "hermes": "Hermes"}
# Official installers: LM Studio's headless daemon + `lms` CLI, and Hermes Agent.
SCRIPT_URLS = {
    "lmstudio": "https://lmstudio.ai/install.sh",
    "hermes": "https://hermes-agent.nousresearch.com/install.sh",
}
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _is_local(url: str) -> bool:
    return (urlparse(url).hostname or "") in ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def lmstudio_missing(cfg: dict) -> bool:
    url = cfg["lmstudio"]["url"]
    if not _is_local(url):
        return False  # remote server: nothing to install here
    if lmstudio._lms_bin() or (Path.home() / ".lmstudio").exists() or shutil.which("lm-studio"):
        return False
    return lmstudio.list_models(url) is None


def hermes_missing(cfg: dict) -> bool:
    if not _is_local(cfg["hermes"]["endpoint"]):
        return False
    home = Path.home()
    return not (shutil.which("hermes") or (home / ".local/bin/hermes").exists() or (home / ".hermes").exists())


def missing(cfg: dict) -> list[str]:
    if not cfg.get("check_components", True):
        return []
    found = []
    if lmstudio_missing(cfg):
        found.append("lmstudio")
    if hermes_missing(cfg):
        found.append("hermes")
    return found


def command_text(name: str) -> str:
    return f"curl -fsSL {SCRIPT_URLS[name]} | bash"


def run(name: str, on_line, on_done) -> None:
    """Runs the installer in a thread; callbacks are invoked from that thread."""

    def work():
        code = 1
        try:
            proc = subprocess.Popen(
                ["bash", "-c", "set -o pipefail; " + command_text(name)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
            )
            for line in proc.stdout:
                on_line(ANSI.sub("", line))
            code = proc.wait()
            if code == 0 and name == "lmstudio" and lmstudio._lms_bin():
                r = subprocess.run([lmstudio._lms_bin(), "server", "start"], capture_output=True, text=True, timeout=60)
                on_line(ANSI.sub("", r.stdout + r.stderr))
        except Exception as e:
            on_line(f"{e}\n")
        on_done(code)

    threading.Thread(target=work, daemon=True).start()
