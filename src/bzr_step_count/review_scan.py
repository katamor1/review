from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .bazaar import BazaarError, fetch_bazaar_diff
from .metrics import aggregate_changes
from .parser import parse_unified_diff
from .review_excel import discover_review_workbooks, read_review_workbook
from .review_metrics import build_review_dataset
from .review_models import (
    DOCUMENT_DENSITY_UNIT_CHARACTERS,
    DOCUMENT_DENSITY_UNIT_PAGES,
    DOCUMENT_PHASES,
    ReviewCase,
    ReviewDataset,
    ValidationMessage,
)
from .review_outputs import write_review_outputs


@dataclass(frozen=True)
class ReviewScanOptions:
    root: str | Path
    output_dir: str | Path | None = None
    start_date: str | date | None = None
    end_date: str | date | None = None
    included_case_ids: tuple[str, ...] | None = None
    excluded_case_ids: tuple[str, ...] = ()
    included_workbook_paths: tuple[str, ...] | None = None
    excluded_workbook_paths: tuple[str, ...] = ()
    skip_bazaar: bool = False
    document_density_unit: str = DOCUMENT_DENSITY_UNIT_PAGES
    write_outputs: bool = True


@dataclass(frozen=True)
class ReviewCaseCandidate:
    case_id: str
    case_name: str
    review_start: str
    review_end: str
    path: str
    validation_status: str
    validation_message_count: int


def scan_review_root(
    root: str | Path,
    output_dir: str | Path,
    *,
    skip_bazaar: bool = False,
    document_density_unit: str = DOCUMENT_DENSITY_UNIT_PAGES,
    write_outputs: bool = True,
) -> ReviewDataset:
    cases, errors = load_review_cases(root, skip_bazaar=skip_bazaar)
    errors = _adjust_document_denominator_errors(cases, errors, document_density_unit)
    dataset = build_review_dataset(cases, validation_errors=errors, document_density_unit=document_density_unit)
    if write_outputs:
        write_review_outputs(dataset, output_dir)
    return dataset


def scan_review_root_with_options(options: ReviewScanOptions) -> ReviewDataset:
    cases, errors = load_review_cases_with_options(options)
    errors = _adjust_document_denominator_errors(cases, errors, options.document_density_unit)
    dataset = build_review_dataset(
        cases,
        validation_errors=errors,
        document_density_unit=options.document_density_unit,
    )
    if options.write_outputs:
        if not options.output_dir:
            raise ValueError("出力先が未指定です")
        write_review_outputs(dataset, options.output_dir)
    return dataset


def validate_review_root(
    root: str | Path,
    output_dir: str | Path | None = None,
    *,
    document_density_unit: str = DOCUMENT_DENSITY_UNIT_PAGES,
    write_outputs: bool = True,
) -> ReviewDataset:
    cases, errors = load_review_cases(root, skip_bazaar=True)
    errors = _adjust_document_denominator_errors(cases, errors, document_density_unit)
    dataset = build_review_dataset(cases, validation_errors=errors, document_density_unit=document_density_unit)
    if output_dir and write_outputs:
        write_review_outputs(dataset, output_dir)
    return dataset


def validate_review_root_with_options(options: ReviewScanOptions) -> ReviewDataset:
    validate_options = ReviewScanOptions(
        root=options.root,
        output_dir=options.output_dir,
        start_date=options.start_date,
        end_date=options.end_date,
        included_case_ids=options.included_case_ids,
        excluded_case_ids=options.excluded_case_ids,
        included_workbook_paths=options.included_workbook_paths,
        excluded_workbook_paths=options.excluded_workbook_paths,
        skip_bazaar=True,
        document_density_unit=options.document_density_unit,
        write_outputs=options.write_outputs,
    )
    return scan_review_root_with_options(validate_options)


def list_review_case_candidates(root: str | Path) -> list[ReviewCaseCandidate]:
    candidates: list[ReviewCaseCandidate] = []
    for workbook_path in discover_review_workbooks(root):
        try:
            case = read_review_workbook(workbook_path)
        except Exception:
            candidates.append(
                ReviewCaseCandidate(
                    case_id="",
                    case_name="",
                    review_start="",
                    review_end="",
                    path=str(workbook_path),
                    validation_status="error",
                    validation_message_count=1,
                )
            )
            continue
        candidates.append(
            ReviewCaseCandidate(
                case_id=case.metadata.case_id,
                case_name=case.metadata.case_name,
                review_start=case.metadata.review_start,
                review_end=case.metadata.review_end,
                path=case.metadata.workbook_path,
                validation_status=_validation_status(case.validation_errors),
                validation_message_count=len(case.validation_errors),
            )
        )
    return candidates


def load_review_cases(
    root: str | Path,
    *,
    skip_bazaar: bool,
    workbook_paths: Iterable[str | Path] | None = None,
) -> tuple[list[ReviewCase], list[ValidationMessage]]:
    root_path = Path(root)
    workbooks = sorted(Path(path) for path in workbook_paths) if workbook_paths is not None else discover_review_workbooks(root_path)
    cases: list[ReviewCase] = []
    errors: list[ValidationMessage] = []

    if not workbooks:
        errors.append(
            ValidationMessage(
                "error",
                "no_workbooks_found",
                "レビュー結果記録表.xlsx が見つかりません",
                path=str(root_path),
            )
        )

    cases, read_errors = _read_review_cases(workbooks)
    errors.extend(read_errors)
    _append_duplicate_case_errors(cases)

    if not skip_bazaar:
        for case in cases:
            _populate_bazaar_metrics(case)

    for case in cases:
        errors.extend(case.validation_errors)

    return cases, errors


def load_review_cases_with_options(options: ReviewScanOptions) -> tuple[list[ReviewCase], list[ValidationMessage]]:
    root_path = Path(options.root)
    workbooks = discover_review_workbooks(root_path)
    errors: list[ValidationMessage] = []
    if not workbooks:
        return [], [
            ValidationMessage(
                "error",
                "no_workbooks_found",
                "レビュー結果記録表.xlsx が見つかりません",
                path=str(root_path),
            )
        ]

    workbooks = _filter_workbook_paths(workbooks, options)
    if not workbooks:
        return [], []

    cases, read_errors = _read_review_cases(workbooks)
    errors.extend(read_errors)
    cases = filter_review_cases(cases, options)
    _append_duplicate_case_errors(cases)

    if not options.skip_bazaar:
        for case in cases:
            _populate_bazaar_metrics(case)

    for case in cases:
        errors.extend(case.validation_errors)

    return cases, errors


def filter_review_cases(cases: list[ReviewCase], options: ReviewScanOptions) -> list[ReviewCase]:
    included_case_ids = set(options.included_case_ids) if options.included_case_ids is not None else None
    excluded_case_ids = set(options.excluded_case_ids)
    included_paths = _normalized_path_set(options.included_workbook_paths) if options.included_workbook_paths is not None else None
    excluded_paths = _normalized_path_set(options.excluded_workbook_paths)

    filtered: list[ReviewCase] = []
    for case in cases:
        case_id = case.metadata.case_id
        path = _normalize_path(case.metadata.workbook_path)
        if included_case_ids is not None and case_id not in included_case_ids:
            continue
        if case_id in excluded_case_ids:
            continue
        if included_paths is not None and path not in included_paths:
            continue
        if path in excluded_paths:
            continue
        if not _case_overlaps_period(case, options.start_date, options.end_date):
            continue
        filtered.append(case)
    return filtered


def _read_review_cases(workbooks: list[Path]) -> tuple[list[ReviewCase], list[ValidationMessage]]:
    cases: list[ReviewCase] = []
    errors: list[ValidationMessage] = []
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

        cases.append(case)

    return cases, errors


def _append_duplicate_case_errors(cases: list[ReviewCase]) -> None:
    seen_case_ids: dict[str, str] = {}
    for case in cases:
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


def _adjust_document_denominator_errors(
    cases: list[ReviewCase],
    errors: list[ValidationMessage],
    document_density_unit: str,
) -> list[ValidationMessage]:
    if str(document_density_unit or DOCUMENT_DENSITY_UNIT_PAGES).strip().lower() != DOCUMENT_DENSITY_UNIT_CHARACTERS:
        return errors

    adjusted = [error for error in errors if error.code != "missing_document_pages"]
    existing = {
        (error.code, error.case_id, error.path, error.message)
        for error in adjusted
    }
    for case in cases:
        metadata = case.metadata
        for phase in DOCUMENT_PHASES:
            if metadata.phase_characters.get(phase, 0) > 0:
                continue
            message = f"{phase}文字数が未入力です"
            key = ("missing_document_characters", metadata.case_id, metadata.workbook_path, message)
            if key in existing:
                continue
            adjusted.append(
                ValidationMessage(
                    "warning",
                    "missing_document_characters",
                    message,
                    path=metadata.workbook_path,
                    case_id=metadata.case_id,
                )
            )
            existing.add(key)
    return adjusted


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
        metadata.bazaar_detected_changed_lines = report.summary.total_changed_lines
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


def _filter_workbook_paths(workbooks: list[Path], options: ReviewScanOptions) -> list[Path]:
    included_paths = _normalized_path_set(options.included_workbook_paths) if options.included_workbook_paths is not None else None
    excluded_paths = _normalized_path_set(options.excluded_workbook_paths)
    filtered: list[Path] = []
    for workbook_path in workbooks:
        normalized = _normalize_path(workbook_path)
        if included_paths is not None and normalized not in included_paths:
            continue
        if normalized in excluded_paths:
            continue
        filtered.append(workbook_path)
    return filtered


def _case_overlaps_period(case: ReviewCase, start: str | date | None, end: str | date | None) -> bool:
    period_start = _parse_date(start)
    period_end = _parse_date(end)
    if period_start and period_end and period_start > period_end:
        raise ValueError("レポート開始日が終了日より後です")

    case_start = _parse_date(case.metadata.review_start)
    case_end = _parse_date(case.metadata.review_end)
    if case_start is None and case_end is None:
        return True
    if case_start is None:
        case_start = case_end
    if case_end is None:
        case_end = case_start
    if period_start and case_end and case_end < period_start:
        return False
    if period_end and case_start and case_start > period_end:
        return False
    return True


def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for candidate in [text, text[:10]]:
        try:
            return date.fromisoformat(candidate.replace("/", "-"))
        except ValueError:
            continue
    return None


def _validation_status(errors: list[ValidationMessage]) -> str:
    if any(error.severity == "error" for error in errors):
        return "error"
    if any(error.severity == "warning" for error in errors):
        return "warning"
    return "ok"


def _normalized_path_set(paths: Iterable[str] | None) -> set[str]:
    if paths is None:
        return set()
    return {_normalize_path(path) for path in paths}


def _normalize_path(path: str | Path) -> str:
    return str(Path(path).resolve(strict=False))
