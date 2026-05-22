from __future__ import annotations

from .review_models import (
    DOCUMENT_PHASES,
    ESCAPE_PHASE,
    METRIC_EXCLUDED_CLASSIFICATIONS,
    PHASE_ORDER,
    CaseSummary,
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
) -> ReviewDataset:
    all_findings = [finding for case in cases for finding in case.findings]
    summaries = [_build_case_summary(case) for case in cases]
    phase_metrics: list[PhaseMetric] = []
    for case in cases:
        phase_metrics.extend(_build_phase_metrics(case))

    return ReviewDataset(
        cases=cases,
        case_summaries=summaries,
        phase_metrics=phase_metrics,
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


def _build_case_summary(case: ReviewCase) -> CaseSummary:
    metadata = case.metadata
    metric = metric_findings(case.findings)
    defects = defect_findings(case.findings)
    minor = [finding for finding in case.findings if finding.is_minor]
    total_known_defects = len(defects) + metadata.escaped_defects
    return CaseSummary(
        case_id=metadata.case_id,
        case_name=metadata.case_name,
        workbook_path=metadata.workbook_path,
        total_findings=len(case.findings),
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


def _build_phase_metrics(case: ReviewCase) -> list[PhaseMetric]:
    metadata = case.metadata
    defects_by_phase = {phase: 0 for phase in PHASE_ORDER}
    for finding in defect_findings(case.findings):
        defects_by_phase[finding.phase] = defects_by_phase.get(finding.phase, 0) + 1

    total_known_defects = sum(defects_by_phase.values()) + metadata.escaped_defects
    cumulative_defects = 0
    rows: list[PhaseMetric] = []
    for phase in PHASE_ORDER:
        phase_findings = [finding for finding in case.findings if finding.phase == phase]
        phase_metric = metric_findings(phase_findings)
        phase_defects = defect_findings(phase_findings)
        cumulative_defects += len(phase_defects)
        denominator_name, denominator_value, density = _density_for_phase(case, phase, len(phase_metric))
        rows.append(
            PhaseMetric(
                case_id=metadata.case_id,
                case_name=metadata.case_name,
                phase=phase,
                total_findings=len(phase_findings),
                metric_findings=len(phase_metric),
                minor_findings=sum(1 for finding in phase_findings if finding.is_minor),
                defect_findings=len(phase_defects),
                cumulative_defects=cumulative_defects,
                escaped_defects=metadata.escaped_defects,
                denominator_name=denominator_name,
                denominator_value=denominator_value,
                finding_density=density,
                character_density_per_1000=_character_density(case, phase, len(phase_metric)),
                defect_removal_rate=_safe_rate(cumulative_defects, total_known_defects),
                escape_rate=_safe_rate(metadata.escaped_defects, total_known_defects),
                open_findings=sum(1 for finding in phase_findings if finding.is_open),
            )
        )

    rows.append(
        PhaseMetric(
            case_id=metadata.case_id,
            case_name=metadata.case_name,
            phase=ESCAPE_PHASE,
            total_findings=metadata.escaped_defects,
            metric_findings=metadata.escaped_defects,
            minor_findings=0,
            defect_findings=metadata.escaped_defects,
            cumulative_defects=cumulative_defects,
            escaped_defects=metadata.escaped_defects,
            denominator_name="最終把握不良件数",
            denominator_value=total_known_defects,
            finding_density=None,
            character_density_per_1000=None,
            defect_removal_rate=_safe_rate(cumulative_defects, total_known_defects),
            escape_rate=_safe_rate(metadata.escaped_defects, total_known_defects),
            open_findings=0,
        )
    )
    return rows


def _density_for_phase(case: ReviewCase, phase: str, metric_count: int) -> tuple[str, float, float | None]:
    if phase == "コード":
        denominator = case.metadata.code_changed_lines
        return "変更ステップ数(KLOC換算)", denominator, _safe_rate(metric_count * 1000, denominator)

    denominator = case.metadata.phase_pages.get(phase, 0)
    if phase in DOCUMENT_PHASES:
        return "レビュー対象ページ数", denominator, _safe_rate(metric_count, denominator)
    return "対象数", denominator, _safe_rate(metric_count, denominator)


def _character_density(case: ReviewCase, phase: str, metric_count: int) -> float | None:
    characters = case.metadata.phase_characters.get(phase, 0)
    if characters <= 0:
        return None
    return _safe_rate(metric_count * 1000, characters)


def _safe_rate(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator
