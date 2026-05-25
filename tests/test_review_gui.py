from __future__ import annotations

import tkinter as tk

import pytest

from bzr_step_count.models import FileChange
from bzr_step_count.metrics import aggregate_changes
from bzr_step_count.review_gui import (
    ReviewStatsGui,
    format_bazaar_diff_log_lines,
    format_step_report_for_gui,
    format_word_document_stats_for_gui,
    load_gui_settings,
    save_gui_settings,
)
from bzr_step_count.review_models import CaseMetadata, ReviewCase, ReviewDataset, ValidationMessage
from bzr_step_count.word_document_service import WordDocumentStats


def _tk_root_or_skip():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"tkinter display is not available: {exc}")
    root.withdraw()
    return root


def test_review_stats_gui_uses_two_tabs(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")
    root = _tk_root_or_skip()
    try:
        app = ReviewStatsGui(root, settings_path)
        labels = [app.notebook.tab(tab_id, "text") for tab_id in app.notebook.tabs()]
        assert labels == ["レビュー統計", "行数カウント"]
        assert app.word_document_button["text"] == "Word文書ページ/文字数取得"
        assert app.word_chars_per_page_var.get() == "1400"
        assert app.document_density_unit_var.get() == "pages"
    finally:
        root.destroy()


def test_format_step_report_for_gui_returns_summary_and_file_rows():
    report = aggregate_changes(
        [
            FileChange(new_path="src/main.py", status="modified", added_lines=2, deleted_lines=1, hunk_count=1),
            FileChange(new_path="logo.bin", status="binary", is_binary=True, ignored_reason="binary"),
        ],
        repository_path="C:/repo",
        from_revision="1",
        to_revision="2",
    )

    summary, rows = format_step_report_for_gui(report)

    assert summary["files_counted"] == 1
    assert summary["files_ignored"] == 1
    assert summary["added"] == 2
    assert summary["deleted"] == 1
    assert rows[0]["path"] == "src/main.py"
    assert rows[0]["total"] == 3


def test_gui_settings_save_and_restore_word_document_path(tmp_path):
    settings_path = tmp_path / "settings.json"
    save_gui_settings(
        settings_path,
        {
            "word_document_path": "C:/docs/spec.docx",
            "word_chars_per_page": "1200",
            "document_density_unit": "characters",
        },
    )

    settings = load_gui_settings(settings_path)

    assert settings["word_document_path"] == "C:/docs/spec.docx"
    assert settings["word_chars_per_page"] == "1200"
    assert settings["document_density_unit"] == "characters"


def test_gui_settings_backfills_word_document_path_for_old_json(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"case_root": "C:/cases"}', encoding="utf-8")

    settings = load_gui_settings(settings_path)

    assert settings["case_root"] == "C:/cases"
    assert settings["word_document_path"] == ""
    assert settings["word_chars_per_page"] == "1400"
    assert settings["document_density_unit"] == "pages"


def test_format_word_document_stats_for_gui_returns_summary_values():
    stats = WordDocumentStats(
        path="C:/docs/spec.docx",
        display_page_count=6,
        page_count_source="estimated",
        metadata_page_count=1,
        estimated_page_count=6,
        character_count_without_whitespace=1200,
        character_count_with_whitespace=1350,
        chars_per_page=1400,
        warnings=["実ページ数を再計算できないため推定ページ数を採用しました"],
    )

    summary = format_word_document_stats_for_gui(stats)

    assert summary == {
        "display_page_count": "6",
        "page_count_source": "estimated",
        "estimated_page_count": "6",
        "metadata_page_count": "1",
        "character_count_without_whitespace": "1,200",
        "character_count_with_whitespace": "1,350",
        "chars_per_page": "1,400",
        "warnings": "実ページ数を再計算できないため推定ページ数を採用しました",
    }


def test_format_bazaar_diff_log_lines_reports_detected_changed_lines():
    dataset = ReviewDataset(
        cases=[
            ReviewCase(
                metadata=CaseMetadata(
                    case_id="CASE-001",
                    bazaar_repo_path="C:/repo",
                    from_revision="r1999",
                    to_revision="r2001",
                    code_changed_lines=14,
                    bazaar_detected_changed_lines=14,
                )
            ),
            ReviewCase(
                metadata=CaseMetadata(
                    case_id="CASE-002",
                    bazaar_repo_path="C:/repo",
                    from_revision="r10",
                    to_revision="r20",
                    code_changed_lines=250,
                )
            ),
        ],
        case_summaries=[],
        phase_metrics=[],
        cross_summaries=[],
        findings=[],
        validation_errors=[
            ValidationMessage(
                "warning",
                "bazaar_diff_failed",
                "Bazaar差分取得に失敗しました: bad revision",
                case_id="CASE-003",
            )
        ],
    )

    lines = format_bazaar_diff_log_lines(dataset, bazaar_enabled=True)

    assert "Bazaar差分: CASE-001 r1999..r2001 検出差分行数 14 行" in lines
    assert "Bazaar差分: CASE-002 取得省略 (Excelのコード変更ステップ数 250 行を使用)" in lines
    assert "Bazaar差分: CASE-003 取得失敗: Bazaar差分取得に失敗しました: bad revision" in lines
    assert format_bazaar_diff_log_lines(dataset, bazaar_enabled=False) == []
