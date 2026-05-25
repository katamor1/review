from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .review_models import DOCUMENT_DENSITY_UNIT_CHARACTERS, DOCUMENT_DENSITY_UNIT_PAGES
from .review_outputs import regenerate_reports_from_sqlite
from .review_scan import scan_review_root, validate_review_root
from .review_template import upgrade_review_workbook_template


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            dataset = validate_review_root(
                args.root,
                args.output,
                document_density_unit=args.document_density_unit,
                write_outputs=bool(args.output),
            )
            _print_validation_summary(dataset)
            return 1 if any(error.severity == "error" for error in dataset.validation_errors) else 0

        if args.command == "scan":
            dataset = scan_review_root(
                args.root,
                args.output,
                skip_bazaar=args.skip_bazaar,
                document_density_unit=args.document_density_unit,
            )
            _print_scan_summary(dataset, args.output)
            return 0

        if args.command == "report":
            regenerate_reports_from_sqlite(args.database, args.output)
            print(f"Report files written to: {Path(args.output)}")
            return 0

        if args.command == "upgrade-template":
            output = upgrade_review_workbook_template(args.source, args.output)
            print(f"Upgraded template written to: {output}")
            return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    parser.print_help(sys.stderr)
    return 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="review-stats")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate review workbook format under a root")
    validate.add_argument("--root", required=True, help="Case root folder or one workbook path")
    validate.add_argument("--output", help="Optional output directory for validation CSV/HTML/SQLite")
    validate.add_argument(
        "--document-density-unit",
        choices=[DOCUMENT_DENSITY_UNIT_PAGES, DOCUMENT_DENSITY_UNIT_CHARACTERS],
        default=DOCUMENT_DENSITY_UNIT_PAGES,
        help="Document review density denominator: pages or characters",
    )

    scan = subparsers.add_parser("scan", help="Scan review workbooks and write metrics")
    scan.add_argument("--root", required=True, help="Case root folder or one workbook path")
    scan.add_argument("--output", required=True, help="Output directory")
    scan.add_argument("--skip-bazaar", action="store_true", help="Do not invoke bzr diff; use Excel code steps only")
    scan.add_argument(
        "--document-density-unit",
        choices=[DOCUMENT_DENSITY_UNIT_PAGES, DOCUMENT_DENSITY_UNIT_CHARACTERS],
        default=DOCUMENT_DENSITY_UNIT_PAGES,
        help="Document review density denominator: pages or characters",
    )

    report = subparsers.add_parser("report", help="Regenerate CSV/HTML reports from review_stats.sqlite")
    report.add_argument("--database", required=True, help="Path to review_stats.sqlite")
    report.add_argument("--output", required=True, help="Output directory")

    upgrade = subparsers.add_parser("upgrade-template", help="Add MVP management sheet and metric columns")
    upgrade.add_argument("--source", required=True, help="Source review workbook")
    upgrade.add_argument("--output", required=True, help="Destination workbook")

    return parser


def _print_validation_summary(dataset) -> None:
    error_count = sum(1 for error in dataset.validation_errors if error.severity == "error")
    warning_count = sum(1 for error in dataset.validation_errors if error.severity == "warning")
    print(f"Cases: {len(dataset.cases)}")
    print(f"Errors: {error_count}")
    print(f"Warnings: {warning_count}")
    for error in dataset.validation_errors[:20]:
        location = f"{error.path}"
        if error.sheet:
            location += f"::{error.sheet}"
        if error.row:
            location += f":{error.row}"
        print(f"[{error.severity}] {error.code}: {error.message} ({location})")


def _print_scan_summary(dataset, output: str) -> None:
    print(f"Cases: {len(dataset.cases)}")
    print(f"Findings: {len(dataset.findings)}")
    print(f"Validation messages: {len(dataset.validation_errors)}")
    print(f"Output: {Path(output)}")


if __name__ == "__main__":
    raise SystemExit(main())
