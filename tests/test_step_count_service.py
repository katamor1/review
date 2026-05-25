from __future__ import annotations

import subprocess

from bzr_step_count.step_count_service import count_bazaar_steps, count_folder_diff_steps


def test_count_bazaar_steps_reuses_existing_diff_counting(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    diff = """=== modified file 'src/main.py'
--- src/main.py
+++ src/main.py
@@ -1 +1,2 @@
-old
+new
+added
"""

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=diff, stderr=""),
    )

    report = count_bazaar_steps(repo, "10", "20")

    assert report.summary.repository_path == str(repo)
    assert report.summary.from_revision == "10"
    assert report.summary.to_revision == "20"
    assert report.summary.total_added_lines == 2
    assert report.summary.total_deleted_lines == 1
    assert report.summary.total_changed_lines == 3
    assert report.files[0].path == "src/main.py"


def test_count_folder_diff_steps_classifies_added_removed_modified_unchanged_and_binary(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (before / "src").mkdir()
    (after / "src").mkdir()
    (before / "src" / "modified.py").write_text("keep\nold\n", encoding="utf-8")
    (after / "src" / "modified.py").write_text("keep\nnew\nadded\n", encoding="utf-8")
    (before / "src" / "removed.py").write_text("gone\nalso gone\n", encoding="utf-8")
    (after / "src" / "added.py").write_text("hello\nworld\n", encoding="utf-8")
    (before / "same.txt").write_text("same\n", encoding="utf-8")
    (after / "same.txt").write_text("same\n", encoding="utf-8")
    (before / "logo.bin").write_bytes(b"\x00\x01before")
    (after / "logo.bin").write_bytes(b"\x00\x01after")
    (before / "meta").mkdir()
    (after / "meta").mkdir()
    (before / "meta" / "history-marker.txt").write_text("main_revno=1999\n", encoding="utf-8")
    (after / "meta" / "history-marker.txt").write_text(
        "main_revno=2000\nThis fixed-size marker is rewritten by synthetic history commits.\n",
        encoding="utf-8",
    )

    report = count_folder_diff_steps(before, after)

    by_path = {change.path: change for change in report.files}
    assert by_path["src/modified.py"].status == "modified"
    assert by_path["src/modified.py"].added_lines == 2
    assert by_path["src/modified.py"].deleted_lines == 1
    assert by_path["src/added.py"].status == "added"
    assert by_path["src/added.py"].added_lines == 2
    assert by_path["src/removed.py"].status == "removed"
    assert by_path["src/removed.py"].deleted_lines == 2
    assert by_path["same.txt"].status == "unchanged"
    assert by_path["same.txt"].total_changed_lines == 0
    assert by_path["logo.bin"].is_binary is True
    assert by_path["logo.bin"].ignored_reason == "binary"
    assert by_path["meta/history-marker.txt"].ignored_reason == "revision management metadata"
    assert by_path["meta/history-marker.txt"].total_changed_lines == 0
    assert report.summary.total_added_lines == 4
    assert report.summary.total_deleted_lines == 3
    assert report.summary.total_changed_lines == 7
