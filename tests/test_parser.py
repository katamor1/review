from bzr_step_count.parser import parse_unified_diff


def test_parser_counts_hunk_changes_without_counting_headers():
    diff = """=== modified file 'src/main.py'
--- src/main.py\t2026-01-01
+++ src/main.py\t2026-01-02
@@ -1,3 +1,4 @@
 context
-old = 1
+old = 2
+added = 3
 unchanged
"""

    result = parse_unified_diff(diff)

    assert result.errors == []
    assert len(result.files) == 1
    change = result.files[0]
    assert change.old_path == "src/main.py"
    assert change.new_path == "src/main.py"
    assert change.path == "src/main.py"
    assert change.status == "modified"
    assert change.added_lines == 2
    assert change.deleted_lines == 1
    assert change.total_changed_lines == 3
    assert change.net_lines == 1
    assert change.hunk_count == 1


def test_parser_ignores_revision_management_hunk_lines():
    diff = """=== modified file 'src/revision-info.txt'
--- src/revision-info.txt
+++ src/revision-info.txt
@@ -1,4 +1,4 @@
 kind=side
-main_revno=1999
-side_revision=3998
+main_revno=2000
+side_revision=4000
-real_deleted_line()
+real_added_line()
"""

    result = parse_unified_diff(diff)

    change = result.files[0]
    assert change.path == "src/revision-info.txt"
    assert change.added_lines == 1
    assert change.deleted_lines == 1
    assert change.total_changed_lines == 2


def test_parser_marks_history_marker_as_revision_management_metadata():
    diff = """=== modified file 'meta/history-marker.txt'
--- meta/history-marker.txt
+++ meta/history-marker.txt
@@ -1,3 +1,4 @@
 kind=side
-main_revno=1999
+main_revno=2000
+This fixed-size marker is rewritten by synthetic history commits.
"""

    result = parse_unified_diff(diff)

    change = result.files[0]
    assert change.path == "meta/history-marker.txt"
    assert change.added_lines == 0
    assert change.deleted_lines == 0
    assert change.ignored_reason == "revision management metadata"


def test_parser_handles_added_removed_multiple_hunks_empty_lines_and_no_newline_marker():
    diff = """=== added file 'src/new.py'
--- /dev/null
+++ src/new.py
@@ -0,0 +1,3 @@
+first
+
+last
\\ No newline at end of file
=== removed file 'src/old.py'
--- src/old.py
+++ /dev/null
@@ -1,2 +0,0 @@
-gone
-also gone
=== modified file 'src/two.py'
--- src/two.py
+++ src/two.py
@@ -1 +1 @@
-a
+b
@@ -10 +10,2 @@
-c
+d
+e
"""

    result = parse_unified_diff(diff)

    by_path = {change.path: change for change in result.files}
    assert by_path["src/new.py"].status == "added"
    assert by_path["src/new.py"].added_lines == 3
    assert by_path["src/new.py"].deleted_lines == 0
    assert by_path["src/old.py"].status == "removed"
    assert by_path["src/old.py"].added_lines == 0
    assert by_path["src/old.py"].deleted_lines == 2
    assert by_path["src/two.py"].hunk_count == 2
    assert by_path["src/two.py"].added_lines == 3
    assert by_path["src/two.py"].deleted_lines == 2


def test_parser_marks_binary_changes_as_report_only():
    diff = """=== modified file 'assets/logo.png'
Binary files assets/logo.png and assets/logo.png differ
"""

    result = parse_unified_diff(diff)

    assert len(result.files) == 1
    change = result.files[0]
    assert change.path == "assets/logo.png"
    assert change.status == "binary"
    assert change.is_binary is True
    assert change.added_lines == 0
    assert change.deleted_lines == 0
    assert "binary" in result.warnings[0].lower()


def test_parser_reads_renamed_file_metadata():
    diff = """=== renamed file 'old/name.py' => 'new/name.py'
--- old/name.py
+++ new/name.py
@@ -1 +1 @@
-old
+new
"""

    result = parse_unified_diff(diff)

    change = result.files[0]
    assert change.status == "renamed"
    assert change.old_path == "old/name.py"
    assert change.new_path == "new/name.py"
    assert change.path == "new/name.py"
    assert change.added_lines == 1
    assert change.deleted_lines == 1
