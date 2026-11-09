"""Remove the app's per-user installation without deleting user configuration."""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import autostart, config, hotkey


class UninstallError(Exception):
    pass


def _confirm(prompt):
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt) as error:
        raise UninstallError("Confirmation interrupted; nothing further was removed") from error


def _safe_path(path, home):
    if not path.is_absolute() or path.is_symlink():
        return False
    resolved = path.resolve()
    root = home.resolve()
    return resolved != root and root in resolved.parents


def _component_paths(home):
    strata_data = Path(os.environ.get("STRATA_DATA_DIR") or
                       (Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share") / "strata"))
    strata_bin = Path(os.environ.get("STRATA_BIN_DIR") or home / ".local/bin") / "strata"
    candidates = {
        "LM Studio / llmster": [home / ".lmstudio", home / ".cache/lm-studio"],
        "Pi": [home / ".pi/agent"],
        "Strata": [strata_data, home / ".strata"],
    }
    if strata_data.name != "strata":
        print(f"Strata data location requires manual review: {strata_data}")
        candidates["Strata"].remove(strata_data)
    if strata_bin.is_symlink() and _safe_path(strata_data, home):
        target = strata_bin.resolve()
        if strata_data.resolve() in target.parents and _safe_path(strata_bin.parent, home):
            candidates["Strata"].insert(0, strata_bin)
        else:
            print(f"Strata executable requires manual review: {strata_bin} -> {target}")
    elif strata_bin.is_symlink():
        print(f"Strata executable requires manual review: {strata_bin}")
    elif strata_bin.exists():
        print(f"Strata executable requires manual review: {strata_bin}")
    result = {}
    for name, paths in candidates.items():
        selected = []
        for path in paths:
            if not path.exists() and not path.is_symlink():
                continue
            if path == strata_bin and path.is_symlink():
                selected.append(path)
            elif _safe_path(path, home):
                selected.append(path)
            else:
                print(f"{name} path requires manual review: {path}")
        if selected:
            result[name] = selected
    return result


def _remove_component_paths(paths, home):
    for path in paths:
        if path.is_symlink():
            if path.name != "strata":
                raise UninstallError(f"Path became a symlink: {path}")
            path.unlink()
        elif not _safe_path(path, home):
            raise UninstallError(f"Unsafe component path: {path}")
        elif path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def _hermes_command(home):
    hermes_home = home / ".hermes"
    configured = Path(os.environ.get("HERMES_HOME") or hermes_home)
    wrapper = home / ".local/bin/hermes"
    if not _safe_path(hermes_home, home) or configured != hermes_home:
        print(f"Hermes location requires manual review: {configured}")
        return None
    if not wrapper.exists():
        if hermes_home.exists() or shutil.which("hermes"):
            print("Hermes installation requires manual removal using its own uninstaller or package manager.")
        return None
    if wrapper.is_symlink():
        recognized = hermes_home.resolve() in wrapper.resolve().parents
    else:
        try:
            with wrapper.open(encoding="utf-8", errors="replace") as stream:
                content = stream.read(8192)
            recognized = "hermes_cli" in content or "hermes-agent" in content
        except OSError:
            recognized = False
    if not recognized or not _safe_path(wrapper.parent, home):
        print(f"Hermes executable requires manual review: {wrapper}")
        return None
    return str(wrapper)


def _preview_hermes(command):
    print(f"\nHermes preview: {command} uninstall --full --dry-run", flush=True)
    try:
        result = subprocess.run([command, "uninstall", "--full", "--dry-run"], timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        raise UninstallError(f"Hermes preview failed: {error}") from error
    if result.returncode:
        raise UninstallError("Hermes preview failed; review its installation manually")


def uninstall():
    try:
        result = subprocess.run(["pipx", "uninstall", "lms-hermes-bridge"],
                                capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        raise UninstallError(str(error)) from error
    if result.returncode:
        raise UninstallError(result.stderr.strip() or result.stdout.strip() or "pipx uninstall failed")
    try:
        autostart.set_enabled(False)
        data = Path.home() / ".local" / "share"
        (data / "applications" / "io.github.lmshermesbridge.desktop").unlink(missing_ok=True)
        (data / "icons" / "hicolor" / "scalable" / "apps" / "io.github.lmshermesbridge.svg").unlink(missing_ok=True)
        if not hotkey.unregister():
            raise UninstallError("Could not remove the GNOME shortcut")
    except OSError as error:
        raise UninstallError(str(error)) from error


def main(argv=None):
    parser = argparse.ArgumentParser(description="Uninstall LMS Hermes Bridge.")
    parser.add_argument("--delete-all", action="store_true", help="Also offer to remove configuration and installed components.")
    args = parser.parse_args(argv)
    if args.delete_all:
        print("Close the bridge and selected components first. This also offers to remove configuration and credentials.")
        print(f"Bridge configuration and keys: {config.CONFIG_DIR} (resolved: {config.CONFIG_DIR.resolve()})")
    else:
        print("This removes LMS Hermes Bridge and its desktop integration. Configuration and other applications remain.")
    try:
        if not _confirm("Continue? [y/N] "):
            print("Uninstall cancelled.")
            return 1
        if args.delete_all:
            home = Path.home()
            path = config.CONFIG_DIR
            if path.is_symlink() or path.name != "lms-hermes-bridge" or not path.is_absolute():
                raise UninstallError(f"Unsafe configuration path: {path}")
            if path.resolve() in (Path("/"), home.resolve()) or path.resolve().name != "lms-hermes-bridge":
                raise UninstallError(f"Unsafe configuration path: {path}")
            choices = []
            for name, paths in _component_paths(home).items():
                print(f"\n{name}: permanently remove these files, including configuration and credentials:")
                for component_path in paths:
                    print(f"  {component_path}")
                if _confirm(f"Remove {name}? [y/N] "):
                    choices.append((name, paths))
                else:
                    print(f"Keeping {name}.")
            hermes = _hermes_command(home)
            remove_hermes = False
            if hermes:
                _preview_hermes(hermes)
                remove_hermes = _confirm("Run the Hermes uninstaller? [y/N] ")
                if not remove_hermes:
                    print("Keeping Hermes.")
            if remove_hermes:
                print("Select full removal and confirm in the Hermes uninstaller.", flush=True)
                result = subprocess.run([hermes, "uninstall", "--full"])
                if result.returncode:
                    raise UninstallError("Hermes uninstall failed; review its output")
                print("Review the Hermes output for cancellations or remaining files.")
            for name, paths in choices:
                _remove_component_paths(paths, home)
                print(f"Removed listed {name} paths.")
            if path.exists():
                shutil.rmtree(path)
            pointer = home / ".lmstudio-home-pointer"
            if pointer.exists():
                print(f"LM Studio location pointer retained; inspect its target manually: {pointer}")
            for variable in ("PI_CODING_AGENT_DIR", "STRATA_HOME"):
                if os.environ.get(variable):
                    print(f"Custom {variable} location requires manual review: {os.environ[variable]}")
            print("Other install locations, external models, backups and cloud credentials may remain.")
            print("Shared system packages are kept. Check shell PATH entries and package-managed installations manually.")
        uninstall()
    except (OSError, UninstallError) as error:
        print(f"Uninstall failed or was incomplete: {error}", file=sys.stderr)
        return 1
    print("LMS Hermes Bridge was uninstalled.")
    return 0