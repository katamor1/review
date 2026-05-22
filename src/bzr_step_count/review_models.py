from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


PHASE_ORDER = ["外部仕様書", "内部仕様書", "コード", "テスト仕様書"]
ESCAPE_PHASE = "後工程/流出"
DOCUMENT_PHASES = ["外部仕様書", "内部仕様書", "テスト仕様書"]
PHASE_SHEET_ALIASES = {
    "外部仕様書": ["外部仕様書"],
    "内部仕様書": ["内部仕様書"],
    "コード": ["コード", "コーディング"],
    "テスト仕様書": ["テスト仕様書"],
}

METRIC_EXCLUDED_CLASSIFICATIONS = {"軽微", "質問", "対象外"}
DEFECT_CLASSIFICATION = "不良"
RESOLVED_STATUSES = {"対応済", "対応不要", "確認済", "完了", "クローズ", "closed", "done"}


@dataclass
class ValidationMessage:
    severity: str
    code: str
    message: str
    path: str = ""
    sheet: str = ""
    row: int | None = None
    case_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CaseMetadata:
    case_id: str
    case_name: str = ""
    workbook_path: str = ""
    bazaar_repo_path: str = ""
    from_revision: str = ""
    to_revision: str = ""
    code_changed_lines: float = 0
    escaped_defects: int = 0
    redmine_issue_id: str = ""
    redmine_url: str = ""
    owner: str = ""
    review_start: str = ""
    review_end: str = ""
    phase_pages: dict[str, float] = field(default_factory=dict)
    phase_characters: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FindingRecord:
    case_id: str
    case_name: str
    workbook_path: str
    phase: str
    sheet: str
    row: int
    number: str
    severity: str
    location: str
    description: str
    response_date: str
    status: str
    notes: str
    classification: str
    metric_target: bool
    detection_phase: str
    origin_phase: str

    @property
    def is_minor(self) -> bool:
        return self.classification == "軽微"

    @property
    def is_defect(self) -> bool:
        return self.metric_target and self.classification == DEFECT_CLASSIFICATION

    @property
    def is_open(self) -> bool:
        return self.status.strip().lower() not in {status.lower() for status in RESOLVED_STATUSES}

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_minor"] = self.is_minor
        data["is_defect"] = self.is_defect
        data["is_open"] = self.is_open
        return data


@dataclass
class ReviewCase:
    metadata: CaseMetadata
    findings: list[FindingRecord] = field(default_factory=list)
    validation_errors: list[ValidationMessage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
            "validation_errors": [error.to_dict() for error in self.validation_errors],
        }


@dataclass
class CaseSummary:
    case_id: str
    case_name: str
    workbook_path: str
    total_findings: int
    metric_findings: int
    minor_findings: int
    defect_findings: int
    escaped_defects: int
    escape_rate: float
    open_findings: int
    code_changed_lines: float
    external_pages: float
    internal_pages: float
    test_pages: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PhaseMetric:
    case_id: str
    case_name: str
    phase: str
    total_findings: int
    metric_findings: int
    minor_findings: int
    defect_findings: int
    cumulative_defects: int
    escaped_defects: int
    denominator_name: str
    denominator_value: float
    finding_density: float | None
    character_density_per_1000: float | None
    defect_removal_rate: float | None
    escape_rate: float | None
    open_findings: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewDataset:
    cases: list[ReviewCase]
    case_summaries: list[CaseSummary]
    phase_metrics: list[PhaseMetric]
    findings: list[FindingRecord]
    validation_errors: list[ValidationMessage]

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": [case.to_dict() for case in self.cases],
            "case_summaries": [summary.to_dict() for summary in self.case_summaries],
            "phase_metrics": [metric.to_dict() for metric in self.phase_metrics],
            "findings": [finding.to_dict() for finding in self.findings],
            "validation_errors": [error.to_dict() for error in self.validation_errors],
        }


def path_text(path: str | Path) -> str:
    return str(Path(path))
