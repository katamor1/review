from __future__ import annotations

from .review_models import (
    DOCUMENT_PHASES,
    ESCAPE_PHASE,
    METRIC_EXCLUDED_CLASSIFICATIONS,
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
) -> ReviewDataset:
    all_findings = [finding for case in cases for finding in case.findings]
    summaries = [_build_case_summary(case) for case in cases]
    phase_metrics: list[PhaseMetric] = []
    for case in cases:
        phase_metrics.extend(_build_phase_metrics(case))
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


def _build_case_summary(case: ReviewCase) -> CaseSummary:
    metadata = case.metadata
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
    defects = defect_findings(case.findings)
    unknown_escaped = _unknown_escaped_defects(case)
    total_known_defects = len(defects) + unknown_escaped
    rows: list[PhaseMetric] = []
    for phase in PHASE_ORDER:
        phase_findings = [finding for finding in case.findings if _normalized_phase(finding.detection_phase) == phase]
        phase_metric = metric_findings(phase_findings)
        phase_defects = defect_findings(phase_findings)
        eligible_defects = [finding for finding in defects if _phase_lte(finding.origin_phase, phase)]
        removed_eligible_defects = [
            finding for finding in eligible_defects if _phase_lte(finding.detection_phase, phase)
        ]
        escaped_from_phase_defects = [
            finding for finding in eligible_defects if _phase_gt(finding.detection_phase, phase)
        ]
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
                cumulative_defects=len(removed_eligible_defects),
                escaped_defects=len(escaped_from_phase_defects),
                eligible_defects=len(eligible_defects),
                removed_eligible_defects=len(removed_eligible_defects),
                escaped_from_phase_defects=len(escaped_from_phase_defects),
                denominator_name=denominator_name,
                denominator_value=denominator_value,
                finding_density=density,
                character_density_per_1000=_character_density(case, phase, len(phase_metric)),
                defect_removal_rate=_safe_rate(len(removed_eligible_defects), len(eligible_defects)),
                escape_rate=_safe_rate(len(escaped_from_phase_defects), len(eligible_defects)),
                open_findings=sum(1 for finding in phase_findings if finding.is_open),
            )
        )

    escaped_phase_findings = [
        finding
        for finding in case.findings
        if _normalized_phase(finding.detection_phase) in {"後工程", "リリース後"}
    ]
    removed_before_escape = [
        finding for finding in defects if _phase_lte(finding.detection_phase, "テスト仕様書")
    ]
    known_escaped = len([finding for finding in defects if _phase_gt(finding.detection_phase, "テスト仕様書")])
    rows.append(
        PhaseMetric(
            case_id=metadata.case_id,
            case_name=metadata.case_name,
            phase=ESCAPE_PHASE,
            total_findings=len(escaped_phase_findings) + unknown_escaped,
            metric_findings=len(metric_findings(escaped_phase_findings)) + unknown_escaped,
            minor_findings=0,
            defect_findings=known_escaped + unknown_escaped,
            cumulative_defects=len(removed_before_escape),
            escaped_defects=metadata.escaped_defects,
            eligible_defects=total_known_defects,
            removed_eligible_defects=len(removed_before_escape),
            escaped_from_phase_defects=metadata.escaped_defects,
            denominator_name="最終把握不良件数",
            denominator_value=total_known_defects,
            finding_density=None,
            character_density_per_1000=None,
            defect_removal_rate=_safe_rate(len(removed_before_escape), total_known_defects),
            escape_rate=_safe_rate(metadata.escaped_defects, total_known_defects),
            open_findings=0,
        )
    )
    return rows


def _unknown_escaped_defects(case: ReviewCase) -> int:
    known_escaped = sum(
        1 for finding in defect_findings(case.findings) if _phase_gt(finding.detection_phase, "テスト仕様書")
    )
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
            metric_findings=len(metric_findings(group)),
            minor_findings=sum(1 for finding in group if finding.is_minor),
            defect_findings=len(defect_findings(group)),
            escaped_defects=sum(1 for finding in defect_findings(group) if _phase_gt(finding.detection_phase, "テスト仕様書")),
            open_findings=sum(1 for finding in group if finding.is_open),
        )
        for key, group in sorted(grouped.items())
    ]


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


def _normalized_phase(phase: str) -> str:
    text = (phase or "").strip()
    if text in {"後工程/流出", "流出"}:
        return "後工程"
    return text or "不明"


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
