import csv
import json
import sqlite3
from pathlib import Path

from openpyxl import Workbook

from bzr_step_count.review_excel import read_review_workbook
from bzr_step_count.review_metrics import build_review_dataset
from bzr_step_count.review_scan import scan_review_root


PHASES = ["外部仕様書", "内部仕様書", "コード", "テスト仕様書"]


def _create_review_workbook(path: Path, *, missing_classification: bool = False) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)

    management = workbook.create_sheet("_集計管理")
    management.append(["項目", "値"])
    rows = [
        ("案件ID", "CASE-001"),
        ("案件名", "注文登録機能"),
        ("Bazaarリポジトリパス", ""),
        ("コードfromリビジョン", "100"),
        ("コードtoリビジョン", "120"),
        ("コード変更ステップ数", 250),
        ("外部仕様書ページ数", 20),
        ("内部仕様書ページ数", 12),
        ("テスト仕様書ページ数", 8),
        ("流出不良件数", 1),
    ]
    for row in rows:
        management.append(row)

    for phase in PHASES:
        sheet = workbook.create_sheet(phase)
        sheet.append(["レビュー者観点チェックリスト"])
        sheet.append(["No", "内容", "状況", "確認日時"])
        sheet.append([1, "観点1", "確認済", "2026-05-22"])
        sheet.append([])
        sheet.append(["指摘項目"])
        headers = ["No", "重大度", "指摘箇所", "指摘内容", "対応日時", "状況", "備考"]
        if not missing_classification:
            headers.extend(["指摘分類", "指標対象", "検出工程", "原因工程"])
        sheet.append(headers)
        if phase == "外部仕様書":
            sheet.append([1, "A", "1章", "要件漏れ", "2026-05-22", "対応済", "", "不良", "対象", phase, "外部仕様書"])
            sheet.append([2, "D", "表紙", "誤字", "2026-05-22", "対応済", "", "軽微", "除外", phase, "外部仕様書"])
        elif phase == "コード":
            sheet.append([1, "B", "src/app.py", "境界値漏れ", "2026-05-22", "対応済", "", "不良", "対象", phase, "コード"])
            sheet.append([2, "C", "src/app.py", "コメント誤字", "2026-05-22", "対応済", "", "軽微", "除外", phase, "コード"])
        else:
            sheet.append([1, "C", "本文", "改善提案", "", "対応保留", "", "改善", "対象", phase, phase])

    workbook.save(path)


def test_read_review_workbook_normalizes_management_and_findings(tmp_path):
    workbook_path = tmp_path / "レビュー結果記録表.xlsx"
    _create_review_workbook(workbook_path)

    case = read_review_workbook(workbook_path)

    assert case.metadata.case_id == "CASE-001"
    assert case.metadata.case_name == "注文登録機能"
    assert case.metadata.phase_pages["外部仕様書"] == 20
    assert case.metadata.code_changed_lines == 250
    assert case.metadata.escaped_defects == 1
    assert {finding.phase for finding in case.findings} == set(PHASES)
    assert any(f.classification == "軽微" and not f.metric_target for f in case.findings)


def test_build_review_dataset_calculates_density_removal_and_escape_rates(tmp_path):
    workbook_path = tmp_path / "レビュー結果記録表.xlsx"
    _create_review_workbook(workbook_path)
    case = read_review_workbook(workbook_path)

    dataset = build_review_dataset([case], validation_errors=[])

    summary = dataset.case_summaries[0]
    assert summary.metric_findings == 4
    assert summary.minor_findings == 2
    assert summary.defect_findings == 2
    assert summary.escaped_defects == 1
    assert summary.escape_rate == 1 / 3

    by_phase = {(row.case_id, row.phase): row for row in dataset.phase_metrics}
    assert by_phase[("CASE-001", "外部仕様書")].finding_density == 1 / 20
    assert by_phase[("CASE-001", "コード")].finding_density == 1 / 250 * 1000
    assert by_phase[("CASE-001", "コード")].defect_removal_rate == 2 / 3


def test_scan_review_root_writes_csv_sqlite_html_and_validation_errors(tmp_path):
    case_dir = tmp_path / "CASE-001"
    case_dir.mkdir()
    _create_review_workbook(case_dir / "レビュー結果記録表.xlsx", missing_classification=True)
    output_dir = tmp_path / "out"

    result = scan_review_root(tmp_path, output_dir, skip_bazaar=True)

    assert len(result.cases) == 1
    assert (output_dir / "case_summary.csv").exists()
    assert (output_dir / "finding_summary.csv").exists()
    assert (output_dir / "phase_metrics.csv").exists()
    assert (output_dir / "monthly_report.html").exists()
    assert (output_dir / "review_stats.sqlite").exists()

    errors = list(csv.DictReader((output_dir / "validation_errors.csv").open(encoding="utf-8-sig")))
    assert any(row["code"] == "missing_finding_columns" for row in errors)

    with sqlite3.connect(output_dir / "review_stats.sqlite") as connection:
        count = connection.execute("select count(*) from findings").fetchone()[0]
    assert count == 6

    payload = json.loads(result.to_json())
    assert payload["case_summaries"][0]["case_id"] == "CASE-001"
