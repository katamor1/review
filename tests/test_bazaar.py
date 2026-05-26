from pathlib import Path
import subprocess

import pytest

from bzr_step_count.bazaar import BazaarError, fetch_bazaar_diff


def test_fetch_bazaar_diff_invokes_bzr_with_argument_array(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="diff text", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = fetch_bazaar_diff(repo, "1000", "1100", paths=["src"], timeout=5)

    assert result.stdout == "diff text"
    assert calls[0][0] == ["bzr", "--no-aliases", "diff", "-r", "1000..1100", "src"]
    assert calls[0][1]["cwd"] == str(repo)
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["timeout"] == 5


def test_fetch_bazaar_diff_ignores_user_command_aliases(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="diff text", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    fetch_bazaar_diff(repo, "1000", "1100")

    assert calls[0][:3] == ["bzr", "--no-aliases", "diff"]


def test_fetch_bazaar_diff_normalizes_display_revision_labels(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="diff text", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    fetch_bazaar_diff(repo, "r1999", "r2001")

    assert calls[0] == ["bzr", "--no-aliases", "diff", "-r", "1999..2001"]


def test_fetch_bazaar_diff_accepts_diff_exit_code_when_stdout_has_diff(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="=== modified file 'a.txt'\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = fetch_bazaar_diff(repo, "1999", "2001")

    assert result.stdout == "=== modified file 'a.txt'\n"


def test_fetch_bazaar_diff_rejects_missing_repo(tmp_path):
    with pytest.raises(BazaarError) as exc:
        fetch_bazaar_diff(tmp_path / "missing", "1", "2")

    assert exc.value.kind == "repo_not_found"


def test_fetch_bazaar_diff_classifies_missing_bzr(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("bzr")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(BazaarError) as exc:
        fetch_bazaar_diff(repo, "1", "2")

    assert exc.value.kind == "bzr_not_found"


def test_fetch_bazaar_diff_classifies_timeout(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(BazaarError) as exc:
        fetch_bazaar_diff(repo, "1", "2", timeout=1)

    assert exc.value.kind == "timeout"


def test_fetch_bazaar_diff_classifies_bzr_errors(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 3, stdout="", stderr="Not a branch")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(BazaarError) as exc:
        fetch_bazaar_diff(repo, "bad", "2")

    assert exc.value.kind == "bzr_error"
    assert "Not a branch" in str(exc.value)
