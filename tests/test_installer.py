import copy
import os
from pathlib import Path
import subprocess

import pytest

from lms_hermes_bridge import installer, lmstudio
from lms_hermes_bridge.config import DEFAULTS


def cfg(**over):
    c = copy.deepcopy(DEFAULTS)
    c.update(over)
    return c


@pytest.mark.skipif(os.name != "posix", reason="requires bash")
@pytest.mark.parametrize("manager", ["pacman", "apt"])
@pytest.mark.parametrize("missing,answer,sudo_result", [
    (True, "y\n", 0), (True, "n\n", 0), (True, "", 0),
    (False, "", 0), (True, "y\n", 1),
])
def test_system_dependency_bootstrap(tmp_path, manager, missing, answer, sudo_result):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls"

    def script(name, body):
        path = bin_dir / name
        path.write_text("#!/bin/bash\n" + body, encoding="utf-8")
        path.chmod(0o755)

    script("dirname", 'printf "%s\\n" "${1%/*}"\n')
    script("sudo", f'printf "sudo %s\\n" "$*" >> "$LOG"\nexit {sudo_result}\n')
    script("pipx", 'printf "pipx %s\\n" "$*" >> "$LOG"\nexit 55\n')
    if manager == "pacman":
        script("pacman", '[[ "$2" != "gtk4" || "$MISSING" != "1" ]]\n')
    else:
        script("apt-get", "exit 0\n")
        script("dpkg-query", '[[ "$3" == "gir1.2-gtk-4.0" && "$MISSING" == "1" ]] || printf installed\n')
    environment = {**os.environ, "PATH": str(bin_dir), "HOME": str(tmp_path), "LOG": str(log),
                   "MISSING": "1" if missing else "0"}
    installer_script = Path(__file__).resolve().parents[1] / "install.sh"
    result = subprocess.run(["/bin/bash", str(installer_script)], input=answer, text=True,
                            capture_output=True, env=environment)
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    if missing and answer == "y\n":
        package = "gtk4" if manager == "pacman" else "gir1.2-gtk-4.0"
        command = "pacman -S --needed --" if manager == "pacman" else "apt-get install --"
        assert f"sudo {command} {package}\n" in calls
        assert ("pipx install" in calls) == (sudo_result == 0)
    elif missing:
        assert not calls and "cancelled" in result.stderr
    else:
        assert "sudo" not in calls and "pipx install" in calls


def test_remote_endpoints_are_never_offered(monkeypatch):
    c = cfg()
    c["lmstudio"]["url"] = "http://192.168.1.5:1234"
    c["hermes"]["endpoint"] = "https://example.org/v1/chat/completions"
    assert installer.missing(c) == []


def test_disabled_check_offers_nothing():
    assert installer.missing(cfg(check_components=False)) == []


def test_missing_detected_when_nothing_present(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(installer.shutil, "which", lambda _n: None)
    monkeypatch.setattr(lmstudio, "_lms_bin", lambda: None)
    monkeypatch.setattr(lmstudio, "list_models", lambda _u: None)
    assert installer.missing(cfg()) == ["lmstudio", "hermes"]


def test_running_server_counts_as_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(installer.shutil, "which", lambda _n: None)
    monkeypatch.setattr(lmstudio, "_lms_bin", lambda: None)
    monkeypatch.setattr(lmstudio, "list_models", lambda _u: [])
    assert installer.missing(cfg()) == ["hermes"]


def test_command_text_uses_official_urls():
    assert installer.command_text("hermes") == "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
    assert installer.command_text("lmstudio").startswith("curl -fsSL https://lmstudio.ai/")
    assert installer.command_text("strata") == (
        "curl -fsSL https://github.com/Niko1221/Strata/releases/latest/download/install.sh | bash"
    )


def test_strata_selection_does_not_offer_lmstudio(monkeypatch):
    monkeypatch.setattr(installer, "lmstudio_missing", lambda _cfg: True)
    monkeypatch.setattr(installer, "hermes_missing", lambda _cfg: False)
    monkeypatch.setattr(installer, "gpu_has_strata_vram", lambda: False)
    assert installer.missing(cfg(local_backend="strata")) == []


def test_strata_offered_only_for_local_missing_server_with_enough_vram(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(installer.shutil, "which", lambda _name: None)
    monkeypatch.setattr(installer.strata, "list_models", lambda _cfg: None)
    monkeypatch.setattr(installer, "hermes_missing", lambda _cfg: False)
    monkeypatch.setattr(installer, "gpu_has_strata_vram", lambda: True)
    config = cfg(local_backend="strata")
    assert installer.missing(config) == ["strata"]
    config["strata"]["url"] = "http://192.168.1.5:8080"
    assert installer.missing(config) == []


def test_nvidia_vram_threshold_is_per_gpu(monkeypatch):
    monkeypatch.setattr(installer.Path, "glob", lambda _path, _pattern: [])
    result = type("Result", (), {"stdout": "11264\n8192\n"})()
    monkeypatch.setattr(installer.subprocess, "run", lambda *_args, **_kwargs: result)
    assert not installer.gpu_has_strata_vram()
    result.stdout = "N/A\n11265\n"
    assert installer.gpu_has_strata_vram()


def test_amd_vram_threshold_and_unavailable_detection(monkeypatch, tmp_path):
    memory = tmp_path / "mem_info_vram_total"
    monkeypatch.setattr(installer.Path, "glob", lambda _path, _pattern: [memory])
    monkeypatch.setattr(installer.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    memory.write_text(str(11 * 1024 ** 3))
    assert not installer.gpu_has_strata_vram()
    memory.write_text(str(11 * 1024 ** 3 + 1))
    assert installer.gpu_has_strata_vram()
    memory.write_text("unknown")
    assert not installer.gpu_has_strata_vram()


def test_strata_not_offered_when_installed_or_server_running(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(installer, "gpu_has_strata_vram", lambda: True)
    monkeypatch.setattr(installer.shutil, "which", lambda _name: "/usr/bin/strata")
    assert not installer.strata_missing(cfg())
    monkeypatch.setattr(installer.shutil, "which", lambda _name: None)
    monkeypatch.setattr(installer.strata, "list_models", lambda _cfg: [])
    assert not installer.strata_missing(cfg())
