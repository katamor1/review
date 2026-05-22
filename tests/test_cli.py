import json
import subprocess

from bzr_step_count import cli


def test_cli_prints_summary_by_default(monkeypatch, tmp_path, capsys):
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

    code = cli.main(["--repo", str(repo), "--from", "1", "--to", "2"])

    assert code == 0
    out = capsys.readouterr().out
    assert "Files counted: 1" in out
    assert "Added:   2" in out
    assert "Deleted: 1" in out


def test_cli_writes_json_output(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    output = tmp_path / "report.json"
    diff = """=== added file 'src/new.py'
--- /dev/null
+++ src/new.py
@@ -0,0 +1 @@
+hello
"""

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=diff, stderr=""),
    )

    code = cli.main(
        ["--repo", str(repo), "--from", "10", "--to", "11", "--format", "json", "--output", str(output)]
    )

    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["total_added_lines"] == 1
    assert payload["files"][0]["path"] == "src/new.py"
