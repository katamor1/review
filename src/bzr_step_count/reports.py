from __future__ import annotations

import csv
import io
import json

from .models import StepReport


CSV_COLUMNS = [
    "path",
    "status",
    "extension",
    "language",
    "added",
    "deleted",
    "total",
    "net",
    "hunks",
    "is_binary",
    "ignored_reason",
]


def render_summary(report: StepReport) -> str:
    summary = report.summary
    lines = [
        f"Repository: {summary.repository_path}",
        f"Revision: {summary.from_revision}..{summary.to_revision}",
        "",
        f"Files counted: {summary.total_files_counted}",
        f"Files ignored: {summary.total_files_ignored}",
        "",
        f"Added:   {summary.total_added_lines:,}",
        f"Deleted: {summary.total_deleted_lines:,}",
        f"Total:   {summary.total_changed_lines:,}",
        f"Net:     {summary.total_net_lines:,}",
    ]
    if report.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in report.warnings)
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"- {error}" for error in report.errors)
    return "\n".join(lines) + "\n"


def render_csv(report: StepReport) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for change in report.files:
        writer.writerow(
            [
                change.path,
                change.status,
                change.extension,
                change.language,
                change.added_lines,
                change.deleted_lines,
                change.total_changed_lines,
                change.net_lines,
                change.hunk_count,
                change.is_binary,
                change.ignored_reason or "",
            ]
        )
    return buffer.getvalue()


def render_json(report: StepReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n"


def render_report(report: StepReport, output_format: str) -> str:
    if output_format == "summary":
        return render_summary(report)
    if output_format == "csv":
        return render_csv(report)
    if output_format == "json":
        return render_json(report)
    raise ValueError(f"Unsupported output format: {output_format}")
