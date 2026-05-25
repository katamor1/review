from __future__ import annotations

from .review_models import (
    DOCUMENT_DENSITY_UNIT_CHARACTERS,
    DOCUMENT_DENSITY_UNIT_PAGES,
    DOCUMENT_DENSITY_UNITS,
    DOCUMENT_PHASES,
    FINAL_PHASE,
    METRIC_EXCLUDED_CLASSIFICATIONS,
    PHASE_ALIASES,
    PHASE_ORDER,
    PHASE_SEQUENCE,
    CaseSummary,
    CrossSummary,
    FindingRecord,
    PhaseMetric,
    ReviewCase,
    ReviewDataset,
    ValidationMessage,
)


def build_review_dataset(
    cases: list[ReviewCase],
    *,
    validation_errors: list[ValidationMessage],
    document_density_unit: str = DOCUMENT_DENSITY_UNIT_PAGES,
) -> ReviewDataset:
    document_density_unit = _normalize_document_density_unit(document_density_unit)
    all_findings = [finding for case in cases for finding in case.findings]
    summaries = [_build_case_summary(case) for case in cases]
    phase_metrics: list[PhaseMetric] = []
    for case in cases:
        phase_metrics.extend(_build_phase_metrics(case, document_density_unit=document_density_unit))
    cross_summaries = _build_cross_summaries(all_findings)

    return ReviewDataset(
        cases=cases,
        case_summaries=summaries,
        phase_metrics=phase_metrics,
        cross_summaries=cross_summaries,
        findings=all_findings,
        validation_errors=validation_errors,
    )


def metric_findings(findings: list[FindingRecord]) -> list[FindingRecord]:
    return [
        finding
        for finding in findings
        if finding.metric_target and finding.classification not in METRIC_EXCLUDED_CLASSIFICATIONS
    ]


def defect_findings(findings: list[FindingRecord]) -> list[FindingRecord]:
    return [finding for finding in metric_findings(findings) if finding.is_defect]


def display_findings(findings: list[FindingRecord]) -> list[FindingRecord]:
    return [finding for finding in findings if not finding.is_minor]


def _build_case_summary(case: ReviewCase) -> CaseSummary:
    metadata = case.metadata
    display = display_findings(case.findings)
    metric = metric_findings(case.findings)
    defects = defect_findings(case.findings)
    minor = [finding for finding in case.findings if finding.is_minor]
    unknown_escaped = _unknown_escaped_defects(case)
    total_known_defects = len(defects) + unknown_escaped
    return CaseSummary(
        case_id=metadata.case_id,
        case_name=metadata.case_name,
        workbook_path=metadata.workbook_path,
        total_findings=len(case.findings),
        display_findings=len(display),
        metric_findings=len(metric),
        minor_findings=len(minor),
        defect_findings=len(defects),
        escaped_defects=metadata.escaped_defects,
        escape_rate=_safe_rate(metadata.escaped_defects, total_known_defects),
        open_findings=sum(1 for finding in case.findings if finding.is_open),
        code_changed_lines=metadata.code_changed_lines,
        external_pages=metadata.phase_pages.get("外部仕様書", 0),
        internal_pages=metadata.phase_pages.get("内部仕様書", 0),
        test_pages=metadata.phase_pages.get("テスト仕様書", 0),
    )


def _build_phase_metrics(case: ReviewCase, *, document_density_unit: str) -> list[PhaseMetric]:
    metadata = case.metadata
    defects = defect_findings(case.findings)
    rows: list[PhaseMetric] = []
    for phase in PHASE_ORDER:
        phase_findings = [finding for finding in case.findings if _normalized_phase(finding.detection_phase) == phase]
        phase_display = display_findings(phase_findings)
        phase_metric = metric_findings(phase_findings)
        phase_defects = defect_findings(phase_findings)
        eligible_defects = [finding for finding in defects if _phase_lte(finding.origin_phase, phase)]
        removed_eligible_defects = [
            finding for finding in eligible_defects if _phase_lte(finding.detection_phase, phase)
        ]
        escaped_from_phase_defects = [
            finding for finding in eligible_defects if _phase_gt(finding.detection_phase, phase)
        ]
        denominator_name, denominator_value, density, density_unit = _density_for_phase(
            case,
            phase,
            len(phase_metric),
            document_density_unit=document_density_unit,
        )
        rows.append(
            PhaseMetric(
                case_id=metadata.case_id,
                case_name=metadata.case_name,
                phase=phase,
                total_findings=len(phase_findings),
                display_findings=len(phase_display),
                metric_findings=len(phase_metric),
                minor_findings=sum(1 for finding in phase_findings if finding.is_minor),
                defect_findings=len(phase_defects),
                cumulative_defects=len(removed_eligible_defects),
                escaped_defects=len(escaped_from_phase_defects),
                eligible_defects=len(eligible_defects),
                removed_eligible_defects=len(removed_eligible_defects),
                escaped_from_phase_defects=len(escaped_from_phase_defects),
                denominator_name=denominator_name,
                denominator_value=denominator_value,
                finding_density=density,
                finding_density_unit=density_unit,
                character_density_per_1000=_character_density(case, phase, len(phase_metric)),
                defect_removal_rate=_safe_rate(len(removed_eligible_defects), len(eligible_defects)),
                escape_rate=_safe_rate(len(escaped_from_phase_defects), len(eligible_defects)),
                open_findings=sum(1 for finding in phase_findings if finding.is_open),
            )
        )
    return rows


def _unknown_escaped_defects(case: ReviewCase) -> int:
    known_escaped = sum(1 for finding in defect_findings(case.findings) if _is_escape_detection(finding))
    return max(case.metadata.escaped_defects - known_escaped, 0)


def _build_cross_summaries(findings: list[FindingRecord]) -> list[CrossSummary]:
    rows: list[CrossSummary] = []
    rows.extend(_summarize_axis("工程", findings, lambda finding: _normalized_phase(finding.detection_phase)))
    rows.extend(_summarize_axis("作業担当者", findings, lambda finding: finding.work_owner or "(未設定)"))
    rows.extend(_summarize_axis("レビュー担当者", findings, lambda finding: finding.reviewer or "(未設定)"))
    rows.extend(_summarize_axis("原因工程", findings, lambda finding: _normalized_phase(finding.origin_phase)))
    rows.extend(_summarize_axis("検出工程", findings, lambda finding: _normalized_phase(finding.detection_phase)))
    return rows


def _summarize_axis(axis: str, findings: list[FindingRecord], key_fn) -> list[CrossSummary]:
    grouped: dict[str, list[FindingRecord]] = {}
    for finding in findings:
        grouped.setdefault(key_fn(finding) or "(未設定)", []).append(finding)
    return [
        CrossSummary(
            axis=axis,
            key=key,
            total_findings=len(group),
            display_findings=len(display_findings(group)),
            metric_findings=len(metric_findings(group)),
            minor_findings=sum(1 for finding in group if finding.is_minor),
            defect_findings=len(defect_findings(group)),
            escaped_defects=sum(1 for finding in defect_findings(group) if _is_escape_detection(finding)),
            open_findings=sum(1 for finding in group if finding.is_open),
        )
        for key, group in sorted(grouped.items())
    ]


def _density_for_phase(
    case: ReviewCase,
    phase: str,
    metric_count: int,
    *,
    document_density_unit: str,
) -> tuple[str, float, float | None, str]:
    if phase == "コード":
        denominator = case.metadata.code_changed_lines
        return "変更ステップ数(KLOC換算)", denominator, _safe_rate(metric_count * 1000, denominator), "件/KLOC"

    if phase in DOCUMENT_PHASES:
        if document_density_unit == DOCUMENT_DENSITY_UNIT_CHARACTERS:
            denominator = case.metadata.phase_characters.get(phase, 0)
            return "レビュー対象文字数", denominator, _safe_rate(metric_count * 1000, denominator), "件/1000文字"
        denominator = case.metadata.phase_pages.get(phase, 0)
        return "レビュー対象ページ数", denominator, _safe_rate(metric_count, denominator), "件/ページ"

    denominator = case.metadata.phase_pages.get(phase, 0)
    return "対象数", denominator, _safe_rate(metric_count, denominator), "件/対象"


def _character_density(case: ReviewCase, phase: str, metric_count: int) -> float | None:
    characters = case.metadata.phase_characters.get(phase, 0)
    if characters <= 0:
        return None
    return _safe_rate(metric_count * 1000, characters)


def _safe_rate(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _normalize_document_density_unit(value: str) -> str:
    unit = (value or DOCUMENT_DENSITY_UNIT_PAGES).strip().lower()
    if unit not in DOCUMENT_DENSITY_UNITS:
        raise ValueError("仕様書の指摘密度単位は pages または characters を指定してください")
    return unit


def _normalized_phase(phase: str) -> str:
    text = (phase or "").strip()
    if text in PHASE_ALIASES:
        return PHASE_ALIASES[text]
    return text or "不明"


def _is_escape_detection(finding: FindingRecord) -> bool:
    return _normalized_phase(finding.detection_phase) == FINAL_PHASE


def _phase_lte(left: str, right: str) -> bool:
    left_order = _phase_order(left)
    right_order = _phase_order(right)
    return left_order is not None and right_order is not None and left_order <= right_order


def _phase_gt(left: str, right: str) -> bool:
    left_order = _phase_order(left)
    right_order = _phase_order(right)
    return left_order is not None and right_order is not None and left_order > right_order


def _phase_order(phase: str) -> int | None:
    normalized = _normalized_phase(phase)
    if normalized not in PHASE_SEQUENCE:
        return None
    return PHASE_SEQUENCE.index(normalized)
