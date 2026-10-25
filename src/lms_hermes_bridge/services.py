"""Starts LM Studio's server and the Hermes gateway in the background when they are not running."""
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from . import lmstudio
from .installer import _is_local


def hermes_health_url(cfg: dict) -> str:
    u = urlparse(cfg["hermes"]["endpoint"])
    return f"{u.scheme}://{u.netloc}/health"


def hermes_bin() -> str | None:
    return shutil.which("hermes") or (str(p) if (p := Path.home() / ".local/bin/hermes").exists() else None)


def lmstudio_up(cfg: dict) -> bool:
    return lmstudio.list_models(cfg["lmstudio"]["url"]) is not None


def hermes_up(cfg: dict) -> bool:
    try:
        with urllib.request.urlopen(hermes_health_url(cfg), timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _run(cmd: list[str]) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=120, stdin=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _wait(check, cfg: dict, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check(cfg):
            return True
        time.sleep(1)
    return check(cfg)


def _start_lmstudio(cfg: dict) -> None:
    lms = lmstudio._lms_bin()
    if lms and not _run([lms, "server", "start"]):
        # Headless setups need the daemon first.
        _run([lms, "daemon", "up"])
        _run([lms, "server", "start"])


def _start_hermes(_cfg: dict) -> None:
    exe = hermes_bin()
    if exe:
        _run([exe, "gateway", "start"])


def _spec(name: str):
    """(is_up, start, endpoint url, installed) resolved at call time."""
    if name == "lmstudio":
        return lmstudio_up, _start_lmstudio, lambda c: c["lmstudio"]["url"], lambda: bool(lmstudio._lms_bin())
    return hermes_up, _start_hermes, lambda c: c["hermes"]["endpoint"], lambda: bool(hermes_bin())


def ensure(cfg: dict, name: str, timeout: float = 60) -> bool:
    """True when the service is reachable afterwards. Only starts local, installed services."""
    is_up, start, url, installed = _spec(name)
    if is_up(cfg):
        return True
    if not cfg.get("autostart_backends", True) or not _is_local(url(cfg)) or not installed():
        return False
    start(cfg)
    return _wait(is_up, cfg, timeout)
