from __future__ import annotations

from pathlib import Path

from .bazaar import BazaarError, fetch_bazaar_diff
from .metrics import aggregate_changes
from .parser import parse_unified_diff
from .review_excel import discover_review_workbooks, read_review_workbook
from .review_metrics import build_review_dataset
from .review_models import ReviewCase, ReviewDataset, ValidationMessage
from .review_outputs import write_review_outputs


def scan_review_root(
    root: str | Path,
    output_dir: str | Path,
    *,
    skip_bazaar: bool = False,
    write_outputs: bool = True,
) -> ReviewDataset:
    cases, errors = load_review_cases(root, skip_bazaar=skip_bazaar)
    dataset = build_review_dataset(cases, validation_errors=errors)
    if write_outputs:
        write_review_outputs(dataset, output_dir)
    return dataset


def validate_review_root(
    root: str | Path,
    output_dir: str | Path | None = None,
    *,
    write_outputs: bool = True,
) -> ReviewDataset:
    cases, errors = load_review_cases(root, skip_bazaar=True)
    dataset = build_review_dataset(cases, validation_errors=errors)
    if output_dir and write_outputs:
        write_review_outputs(dataset, output_dir)
    return dataset


def load_review_cases(root: str | Path, *, skip_bazaar: bool) -> tuple[list[ReviewCase], list[ValidationMessage]]:
    root_path = Path(root)
    workbooks = discover_review_workbooks(root_path)
    cases: list[ReviewCase] = []
    errors: list[ValidationMessage] = []
    seen_case_ids: dict[str, str] = {}

    if not workbooks:
        errors.append(
            ValidationMessage(
                "error",
                "no_workbooks_found",
                "レビュー結果記録表.xlsx が見つかりません",
                path=str(root_path),
            )
        )

    for workbook_path in workbooks:
        try:
            case = read_review_workbook(workbook_path)
        except Exception as exc:
            errors.append(
                ValidationMessage(
                    "error",
                    "workbook_read_failed",
                    f"Excel読取に失敗しました: {exc}",
                    path=str(workbook_path),
                )
            )
            continue

        case_id = case.metadata.case_id
        if case_id in seen_case_ids:
            case.validation_errors.append(
                ValidationMessage(
                    "error",
                    "duplicate_case_id",
                    f"案件IDが重複しています: {case_id}",
                    path=case.metadata.workbook_path,
                    case_id=case_id,
                )
            )
        else:
            seen_case_ids[case_id] = case.metadata.workbook_path

        if not skip_bazaar:
            _populate_bazaar_metrics(case)

        cases.append(case)
        errors.extend(case.validation_errors)

    return cases, errors


def _populate_bazaar_metrics(case: ReviewCase) -> None:
    metadata = case.metadata
    if metadata.code_changed_lines > 0:
        return
    if not (metadata.bazaar_repo_path and metadata.from_revision and metadata.to_revision):
        return
    try:
        diff = fetch_bazaar_diff(
            metadata.bazaar_repo_path,
            metadata.from_revision,
            metadata.to_revision,
        )
        parse_result = parse_unified_diff(diff.stdout)
        report = aggregate_changes(
            parse_result.files,
            repository_path=metadata.bazaar_repo_path,
            from_revision=metadata.from_revision,
            to_revision=metadata.to_revision,
            warnings=parse_result.warnings,
            errors=parse_result.errors,
        )
        metadata.code_changed_lines = report.summary.total_changed_lines
        for warning in parse_result.warnings:
            case.validation_errors.append(
                ValidationMessage(
                    "warning",
                    "bazaar_parse_warning",
                    warning,
                    path=metadata.workbook_path,
                    case_id=metadata.case_id,
                )
            )
    except (BazaarError, OSError, ValueError) as exc:
        case.validation_errors.append(
            ValidationMessage(
                "warning",
                "bazaar_diff_failed",
                f"Bazaar差分取得に失敗しました: {exc}",
                path=metadata.workbook_path,
                case_id=metadata.case_id,
            )
        )
