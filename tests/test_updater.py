from types import SimpleNamespace

import pytest

from lms_hermes_bridge import updater


REMOTE = updater.EXPECTED_REMOTE


def fake_runner(root, behind="0", dirty=""):
    calls = []

    def run(args, cwd=None, capture_output=False, text=False):
        calls.append((args, cwd))
        if args[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=str(root), stderr="")
        if args[:4] == ["git", "remote", "get-url", "origin"]:
            return SimpleNamespace(returncode=0, stdout=REMOTE, stderr="")
        if args[:3] == ["git", "status", "--porcelain"]:
            return SimpleNamespace(returncode=0, stdout=dirty, stderr="")
        if args[:3] == ["git", "branch", "--show-current"]:
            return SimpleNamespace(returncode=0, stdout="main", stderr="")
        if args[:3] == ["git", "rev-list", "--count"]:
            return SimpleNamespace(returncode=0, stdout=behind, stderr="")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    return run, calls


def test_update_fast_forwards_then_reinstalls_with_pipx(tmp_path, monkeypatch):
    run, calls = fake_runner(tmp_path, behind="2")
    monkeypatch.setattr(updater.shutil, "which", lambda _name: "/usr/bin/pipx")
    lines = []
    result = updater.perform_update(lines.append, repo=tmp_path, runner=run)
    assert result == "updated"
    assert any(args[:5] == ["git", "pull", "--ff-only", "origin", "main"] for args, _ in calls)
    assert calls[-1][0] == ["/usr/bin/pipx", "install", "--force", "--system-site-packages", str(tmp_path)]
    assert "Update installed." in lines


def test_update_current_does_not_reinstall(tmp_path, monkeypatch):
    run, calls = fake_runner(tmp_path, behind="0")
    monkeypatch.setattr(updater.shutil, "which", lambda _name: "/usr/bin/pipx")
    assert updater.perform_update(repo=tmp_path, runner=run) == "current"
    assert not any(args[0].endswith("pipx") for args, _ in calls)


def test_update_refuses_dirty_checkout_before_fetch(tmp_path, monkeypatch):
    run, calls = fake_runner(tmp_path, dirty=" M README.md")
    monkeypatch.setattr(updater.shutil, "which", lambda _name: "/usr/bin/pipx")
    with pytest.raises(updater.UpdateError, match="local changes"):
        updater.perform_update(repo=tmp_path, runner=run)
    assert not any(args[:2] == ["git", "fetch"] for args, _ in calls)


def test_update_refuses_non_main_branch(tmp_path):
    run, calls = fake_runner(tmp_path, behind="1")
    old = run

    def feature_runner(args, **kwargs):
        if args[:3] == ["git", "branch", "--show-current"]:
            return SimpleNamespace(returncode=0, stdout="feature/test", stderr="")
        return old(args, **kwargs)

    with pytest.raises(updater.UpdateError, match="main branch"):
        updater.perform_update(repo=tmp_path, runner=feature_runner)
    assert not any(args[:2] == ["git", "fetch"] for args, _ in calls)


def test_periodic_check_only_fetches_and_reports_remote_commits(tmp_path):
    run, calls = fake_runner(tmp_path, behind="3")
    assert updater.updates_available(repo=tmp_path, runner=run)
    assert any(args[:2] == ["git", "fetch"] for args, _ in calls)
    assert not any(args[:2] == ["git", "pull"] for args, _ in calls)


def test_periodic_check_reports_current_checkout(tmp_path):
    run, _calls = fake_runner(tmp_path, behind="0")
    assert not updater.updates_available(repo=tmp_path, runner=run)
