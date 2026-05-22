from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

from .bazaar import BazaarError, fetch_bazaar_diff
from .config import load_config
from .filters import FilterConfig, apply_filters
from .metrics import aggregate_changes
from .parser import parse_unified_diff
from .reports import render_report


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        options = _merge_options(args, config)
        diff = fetch_bazaar_diff(
            options["repo"],
            options["from_revision"],
            options["to_revision"],
            paths=options["paths"],
            timeout=options["timeout"],
        )
        parse_result = parse_unified_diff(diff.stdout)
        changes = apply_filters(parse_result.files, options["filters"])
        warnings = list(parse_result.warnings)
        errors = list(parse_result.errors)

        if args.strict and (warnings or errors):
            for message in warnings + errors:
                print(message, file=sys.stderr)
            return 1

        report = aggregate_changes(
            changes,
            repository_path=str(Path(options["repo"])),
            from_revision=options["from_revision"],
            to_revision=options["to_revision"],
            warnings=warnings,
            errors=errors,
            config=options["config_for_report"],
        )
        rendered = render_report(report, options["format"])
        if options["output"]:
            Path(options["output"]).write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0
    except (BazaarError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bzr-step-count")
    parser.add_argument("--repo", help="Bazaar repository path")
    parser.add_argument("--from", dest="from_revision", help="Source revision")
    parser.add_argument("--to", dest="to_revision", help="Target revision")
    parser.add_argument("--path", dest="paths", action="append", default=[], help="Target path inside the repository")
    parser.add_argument("--include-ext", action="append", default=[], help="Comma-separated extensions to include")
    parser.add_argument("--exclude", action="append", default=[], help="Glob pattern to exclude")
    parser.add_argument("--config", help="TOML, JSON, or simple YAML config file")
    parser.add_argument("--format", choices=["summary", "csv", "json"], help="Output format")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--strict", action="store_true", help="Treat parse warnings as errors")
    parser.add_argument("--timeout", type=float, help="bzr diff timeout in seconds")
    return parser


def _merge_options(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    repository = config.get("repository", {})
    revision = config.get("revision", {})
    filters = config.get("filters", {})
    output = config.get("output", {})

    repo = args.repo or repository.get("path") or "."
    from_revision = args.from_revision or revision.get("from")
    to_revision = args.to_revision or revision.get("to")
    if not from_revision or not to_revision:
        raise ValueError("--from and --to are required unless provided by config")

    include_ext = _normalize_extensions(
        _flatten_csv(args.include_ext) or filters.get("include_extensions") or []
    )
    exclude_ext = _normalize_extensions(filters.get("exclude_extensions") or [])
    exclude_patterns = list(filters.get("exclude_patterns") or []) + list(args.exclude or [])

    filter_config = FilterConfig(
        include_extensions=include_ext or None,
        exclude_extensions=exclude_ext or None,
        include_paths=list(filters.get("include_paths") or []),
        exclude_paths=list(filters.get("exclude_paths") or []),
        exclude_patterns=exclude_patterns,
    )

    output_format = args.format or output.get("format") or "summary"
    if output_format not in {"summary", "csv", "json"}:
        raise ValueError(f"Unsupported output format: {output_format}")

    return {
        "repo": repo,
        "from_revision": str(from_revision),
        "to_revision": str(to_revision),
        "paths": args.paths or list(config.get("paths", []) or []),
        "timeout": args.timeout if args.timeout is not None else config.get("timeout", 60),
        "filters": filter_config,
        "format": output_format,
        "output": args.output or output.get("file"),
        "config_for_report": {
            "format": output_format,
            "include_extensions": sorted(include_ext),
            "exclude_extensions": sorted(exclude_ext),
            "exclude_patterns": exclude_patterns,
        },
    }


def _flatten_csv(values: list[str]) -> list[str]:
    flattened: list[str] = []
    for value in values:
        flattened.extend(part.strip() for part in value.split(",") if part.strip())
    return flattened


def _normalize_extensions(values: list[str]) -> set[str]:
    normalized = set()
    for value in values:
        item = str(value).strip().lower()
        if not item:
            continue
        normalized.add(item if item.startswith(".") else f".{item}")
    return normalized
