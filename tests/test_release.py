from __future__ import annotations

from bzr_step_count import release


def test_no_arguments_launches_gui(monkeypatch):
    calls: list[object] = []
    monkeypatch.setattr(release, "_detach_console_for_gui", lambda: calls.append("detach"))
    monkeypatch.setattr(release, "_run_gui", lambda: calls.append("gui") or 7)

    assert release.main([]) == 7
    assert calls == ["detach", "gui"]


def test_direct_review_subcommand_is_forwarded(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(release, "_run_review_cli", lambda args: calls.append(args) or 3)

    assert release.main(["scan", "--root", "cases", "--output", "out"]) == 3
    assert calls == [["scan", "--root", "cases", "--output", "out"]]


def test_explicit_stats_prefix_is_removed(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(release, "_run_review_cli", lambda args: calls.append(args) or 4)

    assert release.main(["stats", "validate", "--root", "cases"]) == 4
    assert calls == [["validate", "--root", "cases"]]


def test_count_prefix_is_removed(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(release, "_run_step_cli", lambda args: calls.append(args) or 5)

    assert release.main(["count", "--repo", ".", "--from", "1", "--to", "2"]) == 5
    assert calls == [["--repo", ".", "--from", "1", "--to", "2"]]


def test_help_prints_unified_usage(capsys):
    assert release.main(["--help"]) == 0

    output = capsys.readouterr().out
    assert "review-stats.exe" in output
    assert "scan" in output
    assert "count" in output


def test_unknown_mode_returns_usage_error(capsys):
    assert release.main(["unknown-mode"]) == 2

    captured = capsys.readouterr()
    assert "unknown-mode" in captured.err
    assert "review-stats.exe" in captured.err
