"""Safe self-update from the clean Git checkout used to install the pipx app."""
import json
import shlex
import shutil
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path
from urllib.parse import unquote, urlparse

EXPECTED_REMOTE = "https://github.com/datenklo/lms-hermes-bridge.git"
ALLOWED_REMOTES = {EXPECTED_REMOTE, "git@github.com:datenklo/lms-hermes-bridge.git"}


class UpdateError(Exception):
    pass


def _git(args: list[str], repo: Path, runner=subprocess.run):
    result = runner(["git", *args], cwd=repo, capture_output=True, text=True)
    if result.returncode:
        message = (result.stderr or result.stdout or "git command failed").strip()
        raise UpdateError(message)
    return (result.stdout or "").strip()


def _is_expected_checkout(path: Path, runner=subprocess.run) -> bool:
    try:
        root = Path(_git(["rev-parse", "--show-toplevel"], path, runner)).resolve()
        remote = _git(["remote", "get-url", "origin"], root, runner)
        return remote in ALLOWED_REMOTES
    except (OSError, UpdateError):
        return False


def discover_checkout() -> Path:
    """Find source checkout via pip's PEP 610 metadata, or the current source tree."""
    try:
        raw = distribution("lms-hermes-bridge").read_text("direct_url.json")
        if raw:
            url = json.loads(raw).get("url", "")
            parsed = urlparse(url)
            if parsed.scheme == "file":
                candidate = Path(unquote(parsed.path)).expanduser().resolve()
                if _is_expected_checkout(candidate):
                    return Path(_git(["rev-parse", "--show-toplevel"], candidate))
    except Exception:
        pass

    for parent in Path(__file__).resolve().parents:
        if _is_expected_checkout(parent):
            return Path(_git(["rev-parse", "--show-toplevel"], parent))
    raise UpdateError("The LMS Hermes Bridge Git checkout could not be found.")


def updates_available(repo: Path | None = None, runner=subprocess.run) -> bool:
    """Fetch remote refs only, then compare the current commit with origin/main."""
    root = Path(repo or discover_checkout()).resolve()
    if not _is_expected_checkout(root, runner):
        raise UpdateError("The selected folder is not the official LMS Hermes Bridge checkout.")
    branch = _git(["branch", "--show-current"], root, runner)
    if branch != "main":
        raise UpdateError(f"Update checks are only supported from the main branch (current: {branch}).")
    _git(["fetch", "--quiet", "--prune", "origin"], root, runner)
    behind = int(_git(["rev-list", "--count", "HEAD..origin/main"], root, runner) or "0")
    return behind > 0


def perform_update(on_line=lambda _line: None, repo: Path | None = None, runner=subprocess.run) -> str:
    """Fast-forward the source checkout and reinstall the pipx app. Returns updated/current."""
    root = Path(repo or discover_checkout()).resolve()
    if not _is_expected_checkout(root, runner):
        raise UpdateError("The selected folder is not the official LMS Hermes Bridge checkout.")
    dirty = _git(["status", "--porcelain", "--untracked-files=normal"], root, runner)
    if dirty:
        raise UpdateError("The update checkout has local changes. Commit or move them before updating.")
    branch = _git(["branch", "--show-current"], root, runner)
    if branch != "main":
        raise UpdateError(f"Self-update is only supported from the main branch (current: {branch}).")

    on_line("Fetching origin/main…")
    _git(["fetch", "--prune", "origin"], root, runner)
    behind = int(_git(["rev-list", "--count", "HEAD..@{u}"], root, runner) or "0")
    if behind == 0:
        on_line("Already up to date.")
        return "current"

    on_line(f"Applying {behind} commit(s) from origin/main…")
    _git(["pull", "--ff-only", "origin", "main"], root, runner)

    pipx = shutil.which("pipx")
    if not pipx:
        raise UpdateError("pipx was not found. Install updates with install.sh instead.")
    on_line("Reinstalling the application with pipx…")
    result = runner([pipx, "install", "--force", "--system-site-packages", str(root)],
                    capture_output=True, text=True)
    if result.returncode:
        raise UpdateError((result.stderr or result.stdout or "pipx install failed").strip())
    output = (result.stdout or "").strip()
    if output:
        on_line(output)
    on_line("Update installed.")
    return "updated"


def restart_command() -> list[str]:
    """Return a argv safe to pass to Popen after the current GTK application exits."""
    from .hotkey import launch_command

    executable = shutil.which("lms-hermes-bridge")
    return [executable] if executable else shlex.split(launch_command())
