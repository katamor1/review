import json

from bzr_step_count.filters import FilterConfig, apply_filters
from bzr_step_count.metrics import aggregate_changes
from bzr_step_count.models import FileChange
from bzr_step_count.reports import render_csv, render_json, render_summary


def test_filters_mark_unmatched_extensions_and_excluded_patterns_as_ignored():
    changes = [
        FileChange(new_path="src/main.py", status="modified", added_lines=2, deleted_lines=1, hunk_count=1),
        FileChange(new_path="dist/app.js", status="modified", added_lines=10, deleted_lines=0, hunk_count=1),
        FileChange(new_path="README.md", status="modified", added_lines=1, deleted_lines=0, hunk_count=1),
    ]
    config = FilterConfig(include_extensions={".py"}, exclude_patterns=["dist/*"])

    filtered = apply_filters(changes, config)

    by_path = {change.path: change for change in filtered}
    assert by_path["src/main.py"].ignored_reason is None
    assert by_path["dist/app.js"].ignored_reason == "excluded by pattern: dist/*"
    assert by_path["README.md"].ignored_reason == "extension not included: .md"


def test_metrics_aggregate_counted_ignored_extension_and_directory_totals():
    changes = [
        FileChange(new_path="src/main.py", status="modified", added_lines=2, deleted_lines=1, hunk_count=1),
        FileChange(new_path="src/util.py", status="modified", added_lines=1, deleted_lines=1, hunk_count=1),
        FileChange(new_path="assets/logo.png", status="binary", is_binary=True, ignored_reason="binary"),
    ]

    report = aggregate_changes(changes, repository_path=".", from_revision="1", to_revision="2")

    assert report.summary.total_files_changed == 3
    assert report.summary.total_files_counted == 2
    assert report.summary.total_files_ignored == 1
    assert report.summary.total_added_lines == 3
    assert report.summary.total_deleted_lines == 2
    assert report.summary.total_changed_lines == 5
    assert report.summary.total_net_lines == 1
    assert report.extensions[".py"].total_changed_lines == 5
    assert report.directories["src"].total_changed_lines == 5


def test_reports_render_summary_csv_and_json():
    changes = [
        FileChange(new_path="src/main.py", status="modified", added_lines=2, deleted_lines=1, hunk_count=1),
        FileChange(new_path="assets/logo.png", status="binary", is_binary=True, ignored_reason="binary"),
    ]
    report = aggregate_changes(
        changes,
        repository_path="C:/repo",
        from_revision="1000",
        to_revision="1100",
        warnings=["binary file skipped"],
        config={"format": "json"},
    )

    summary = render_summary(report)
    assert "Repository: C:/repo" in summary
    assert "Revision: 1000..1100" in summary
    assert "Added:   2" in summary
    assert "Deleted: 1" in summary

    csv_text = render_csv(report)
    assert "path,status,extension,language,added,deleted,total,net,hunks,is_binary,ignored_reason" in csv_text
    assert "src/main.py,modified,.py,Python,2,1,3,1,1,False," in csv_text

    payload = json.loads(render_json(report))
    assert payload["schema_version"] == "1.0"
    assert payload["summary"]["total_changed_lines"] == 3
    assert payload["files"][1]["is_binary"] is True
    assert payload["warnings"] == ["binary file skipped"]
