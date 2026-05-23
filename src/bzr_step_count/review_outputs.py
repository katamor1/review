from __future__ import annotations

import csv
from dataclasses import fields
from html import escape
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from .review_models import CaseSummary, CrossSummary, FindingRecord, PhaseMetric, ReviewDataset, ValidationMessage


DISPLAY_LABELS = {
    "case_id": "案件ID",
    "case_name": "案件名",
    "workbook_path": "レビュー結果記録表",
    "total_findings": "指摘件数",
    "metric_findings": "指標対象指摘件数",
    "minor_findings": "軽微指摘件数",
    "defect_findings": "不良指摘件数",
    "escaped_defects": "流出不良件数",
    "eligible_defects": "除去可能不良件数",
    "removed_eligible_defects": "対象工程までに除去した不良件数",
    "escaped_from_phase_defects": "対象工程から流出した不良件数",
    "escape_rate": "流出率",
    "open_findings": "未対応指摘件数",
    "code_changed_lines": "コード変更ステップ数",
    "external_pages": "外部仕様書ページ数",
    "internal_pages": "内部仕様書ページ数",
    "test_pages": "テスト仕様書ページ数",
    "phase": "工程",
    "cumulative_defects": "累積検出不良件数",
    "denominator_name": "密度分母",
    "denominator_value": "分母値",
    "finding_density": "指摘密度",
    "character_density_per_1000": "1000文字あたり指摘密度",
    "defect_removal_rate": "不良除去率",
    "severity": "重大度",
    "code": "コード",
    "message": "メッセージ",
    "path": "パス",
    "sheet": "シート",
    "row": "行",
    "number": "No",
    "location": "指摘箇所",
    "description": "指摘内容",
    "response_date": "対応日時",
    "status": "状況",
    "notes": "備考",
    "classification": "指摘分類",
    "metric_target": "指標対象",
    "detection_phase": "検出工程",
    "origin_phase": "原因工程",
    "work_owner": "作業担当者",
    "reviewer": "レビュー担当者",
    "axis": "集計軸",
    "key": "集計値",
}


def write_review_outputs(dataset: ReviewDataset, output_dir: str | Path) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    _write_csv(output_path / "case_summary.csv", dataset.case_summaries, CaseSummary)
    _write_csv(output_path / "finding_summary.csv", dataset.findings, FindingRecord)
    _write_csv(output_path / "phase_metrics.csv", dataset.phase_metrics, PhaseMetric)
    _write_csv(output_path / "cross_summary.csv", dataset.cross_summaries, CrossSummary)
    _write_csv(output_path / "phase_summary.csv", _filter_cross_summaries(dataset.cross_summaries, "工程"), CrossSummary)
    _write_csv(output_path / "owner_summary.csv", _filter_cross_summaries(dataset.cross_summaries, "作業担当者"), CrossSummary)
    _write_csv(output_path / "reviewer_summary.csv", _filter_cross_summaries(dataset.cross_summaries, "レビュー担当者"), CrossSummary)
    _write_csv(output_path / "validation_errors.csv", dataset.validation_errors, ValidationMessage)
    _write_sqlite(output_path / "review_stats.sqlite", dataset)
    _write_html(output_path / "monthly_report.html", dataset)


def regenerate_reports_from_sqlite(database_path: str | Path, output_dir: str | Path) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        for table_name, file_name in [
            ("case_summaries", "case_summary.csv"),
            ("findings", "finding_summary.csv"),
            ("phase_metrics", "phase_metrics.csv"),
            ("cross_summaries", "cross_summary.csv"),
            ("validation_errors", "validation_errors.csv"),
        ]:
            rows = connection.execute(f"select * from {table_name}").fetchall()
            _write_csv_dicts(output_path / file_name, [dict(row) for row in rows])

        summaries = [dict(row) for row in connection.execute("select * from case_summaries").fetchall()]
        metrics = [dict(row) for row in connection.execute("select * from phase_metrics").fetchall()]
        cross_summaries = [dict(row) for row in connection.execute("select * from cross_summaries").fetchall()]
        errors = [dict(row) for row in connection.execute("select * from validation_errors").fetchall()]
    _write_csv_dicts(output_path / "phase_summary.csv", [row for row in cross_summaries if row["axis"] == "工程"])
    _write_csv_dicts(output_path / "owner_summary.csv", [row for row in cross_summaries if row["axis"] == "作業担当者"])
    _write_csv_dicts(output_path / "reviewer_summary.csv", [row for row in cross_summaries if row["axis"] == "レビュー担当者"])
    _write_html_from_dicts(output_path / "monthly_report.html", summaries, metrics, cross_summaries, errors)


def _write_csv(path: Path, rows: Iterable[Any], row_type: type[Any]) -> None:
    field_names = [field.name for field in fields(row_type)]
    display_names = [_display_label(field_name) for field_name in field_names]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=display_names)
        writer.writeheader()
        for row in rows:
            row_dict = row.to_dict()
            writer.writerow(
                {
                    _display_label(field_name): _csv_value(row_dict.get(field_name))
                    for field_name in field_names
                }
            )


def _write_csv_dicts(path: Path, rows: list[dict[str, Any]]) -> None:
    field_names = list(rows[0].keys()) if rows else []
    display_names = [_display_label(field_name) for field_name in field_names]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=display_names)
        if field_names:
            writer.writeheader()
            for row in rows:
                writer.writerow({_display_label(field_name): row.get(field_name) for field_name in field_names})


def _write_sqlite(path: Path, dataset: ReviewDataset) -> None:
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as connection:
        _create_table(connection, "case_summaries", CaseSummary)
        _create_table(connection, "findings", FindingRecord)
        _create_table(connection, "phase_metrics", PhaseMetric)
        _create_table(connection, "cross_summaries", CrossSummary)
        _create_table(connection, "validation_errors", ValidationMessage)
        _insert_dataclass_rows(connection, "case_summaries", dataset.case_summaries, CaseSummary)
        _insert_dataclass_rows(connection, "findings", dataset.findings, FindingRecord)
        _insert_dataclass_rows(connection, "phase_metrics", dataset.phase_metrics, PhaseMetric)
        _insert_dataclass_rows(connection, "cross_summaries", dataset.cross_summaries, CrossSummary)
        _insert_dataclass_rows(connection, "validation_errors", dataset.validation_errors, ValidationMessage)


def _create_table(connection: sqlite3.Connection, table_name: str, row_type: type[Any]) -> None:
    columns = []
    for field in fields(row_type):
        column_type = "REAL" if field.type in {float, "float"} else "TEXT"
        if field.type in {int, "int"}:
            column_type = "INTEGER"
        columns.append(f"{field.name} {column_type}")
    connection.execute(f"create table {table_name} ({', '.join(columns)})")


def _insert_dataclass_rows(
    connection: sqlite3.Connection,
    table_name: str,
    rows: Iterable[Any],
    row_type: type[Any],
) -> None:
    field_names = [field.name for field in fields(row_type)]
    placeholders = ", ".join("?" for _ in field_names)
    sql = f"insert into {table_name} ({', '.join(field_names)}) values ({placeholders})"
    connection.executemany(
        sql,
        [[_sqlite_value(row.to_dict().get(field_name)) for field_name in field_names] for row in rows],
    )


def _write_html(path: Path, dataset: ReviewDataset) -> None:
    _write_html_from_dicts(
        path,
        [summary.to_dict() for summary in dataset.case_summaries],
        [metric.to_dict() for metric in dataset.phase_metrics],
        [summary.to_dict() for summary in dataset.cross_summaries],
        [error.to_dict() for error in dataset.validation_errors],
    )


def _write_html_from_dicts(
    path: Path,
    summaries: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    cross_summaries: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    total_cases = len(summaries)
    total_metric = sum(int(row.get("metric_findings") or 0) for row in summaries)
    total_minor = sum(int(row.get("minor_findings") or 0) for row in summaries)
    total_escaped = sum(int(row.get("escaped_defects") or 0) for row in summaries)
    body = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>レビュー統計レポート</title>
  <style>
    body {{ font-family: "Yu Gothic", "Meiryo", sans-serif; margin: 24px; color: #1f2933; }}
    h1, h2 {{ margin: 0 0 12px; }}
    section {{ margin: 24px 0; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
    th, td {{ border: 1px solid #d0d7de; padding: 6px 8px; font-size: 13px; }}
    th {{ background: #f6f8fa; text-align: left; }}
    .kpi {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; }}
    .box {{ border: 1px solid #d0d7de; border-radius: 6px; padding: 12px; }}
    .value {{ font-size: 24px; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>レビュー統計レポート</h1>
  <section class="kpi">
    <div class="box"><div>案件数</div><div class="value">{total_cases}</div></div>
    <div class="box"><div>指標対象指摘</div><div class="value">{total_metric}</div></div>
    <div class="box"><div>軽微指摘</div><div class="value">{total_minor}</div></div>
    <div class="box"><div>流出不良</div><div class="value">{total_escaped}</div></div>
  </section>
  <section>
    <h2>案件別サマリー</h2>
    {_html_table(summaries, ["case_id", "case_name", "metric_findings", "minor_findings", "defect_findings", "escaped_defects", "escape_rate", "open_findings"])}
  </section>
  <section>
    <h2>工程別指標</h2>
    {_html_table(metrics, ["case_id", "phase", "metric_findings", "minor_findings", "eligible_defects", "escaped_from_phase_defects", "finding_density", "defect_removal_rate", "escape_rate", "open_findings"])}
  </section>
  <section>
    <h2>工程横断サマリー</h2>
    {_html_table(_filter_dict_summaries(cross_summaries, "工程"), ["key", "metric_findings", "minor_findings", "defect_findings", "escaped_defects", "open_findings"])}
  </section>
  <section>
    <h2>作業担当者別サマリー</h2>
    {_html_table(_filter_dict_summaries(cross_summaries, "作業担当者"), ["key", "metric_findings", "minor_findings", "defect_findings", "escaped_defects", "open_findings"])}
  </section>
  <section>
    <h2>レビュー担当者別サマリー</h2>
    {_html_table(_filter_dict_summaries(cross_summaries, "レビュー担当者"), ["key", "metric_findings", "minor_findings", "defect_findings", "escaped_defects", "open_findings"])}
  </section>
  <section>
    <h2>品質警告</h2>
    {_html_table(errors, ["severity", "code", "case_id", "sheet", "row", "message", "path"])}
  </section>
</body>
</html>
"""
    path.write_text(body, encoding="utf-8")


def _filter_cross_summaries(rows: list[CrossSummary], axis: str) -> list[CrossSummary]:
    return [row for row in rows if row.axis == axis]


def _filter_dict_summaries(rows: list[dict[str, Any]], axis: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("axis") == axis]


def _html_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "<p>該当データはありません。</p>"
    header = "".join(f"<th>{escape(_display_label(column))}</th>" for column in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{escape(_format_html_value(row.get(column)))}</td>" for column in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _format_html_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if value is None:
        return ""
    return str(value)


def _display_label(field_name: str) -> str:
    return DISPLAY_LABELS.get(field_name, field_name)


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return value


def _sqlite_value(value: Any) -> Any:
    if isinstance(value, bool):
        return 1 if value else 0
    return value
