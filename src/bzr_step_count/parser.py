from __future__ import annotations

from dataclasses import dataclass, field
import re

from .models import FileChange, normalize_path


@dataclass
class ParseResult:
    files: list[FileChange] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


_META_RE = re.compile(
    r"^===\s+(?P<status>added|modified|removed|renamed|kind changed)\s+file\s+'(?P<path>[^']+)'"
    r"(?:\s+=>\s+'(?P<new>[^']+)')?"
)


def parse_unified_diff(diff_text: str) -> ParseResult:
    result = ParseResult()
    current: FileChange | None = None
    in_hunk = False

    def finish_current() -> None:
        nonlocal current
        if current is not None:
            current.__post_init__()
            result.files.append(current)
            current = None

    for raw_line in diff_text.splitlines():
        line = raw_line.rstrip("\n")

        if line.startswith("=== "):
            finish_current()
            current = _change_from_bazaar_metadata(line)
            in_hunk = False
            continue

        if _looks_binary_line(line):
            if current is None:
                current = FileChange(status="binary")
            current.status = "binary"
            current.is_binary = True
            current.ignored_reason = current.ignored_reason or "binary"
            result.warnings.append(f"Binary diff skipped for {current.path or 'unknown file'}")
            in_hunk = False
            continue

        if line.startswith("--- "):
            if current is None:
                current = FileChange(status="unknown")
            path = _parse_file_header_path(line[4:])
            if path != "/dev/null":
                current.old_path = path
            in_hunk = False
            continue

        if line.startswith("+++ "):
            if current is None:
                current = FileChange(status="unknown")
            path = _parse_file_header_path(line[4:])
            if path != "/dev/null":
                current.new_path = path
            in_hunk = False
            continue

        if line.startswith("@@"):
            if current is None:
                current = FileChange(status="unknown")
            current.hunk_count += 1
            in_hunk = True
            continue

        if in_hunk:
            if line.startswith("\\ No newline"):
                continue
            if line.startswith("+"):
                current.added_lines += 1
                continue
            if line.startswith("-"):
                current.deleted_lines += 1
                continue

    finish_current()
    return result


def _change_from_bazaar_metadata(line: str) -> FileChange:
    match = _META_RE.match(line)
    if not match:
        return FileChange(status="unknown")

    status = match.group("status")
    path = normalize_path(match.group("path"))
    new_path = normalize_path(match.group("new"))

    if status == "added":
        return FileChange(new_path=path, status="added")
    if status == "removed":
        return FileChange(old_path=path, status="removed")
    if status == "renamed":
        return FileChange(old_path=path, new_path=new_path, status="renamed")
    if status == "modified":
        return FileChange(old_path=path, new_path=path, status="modified")
    if status == "kind changed":
        return FileChange(old_path=path, new_path=path, status="kind_changed")
    return FileChange(old_path=path, new_path=new_path or path, status=status)


def _parse_file_header_path(header_value: str) -> str | None:
    cleaned = header_value.strip()
    if "\t" in cleaned:
        cleaned = cleaned.split("\t", 1)[0]
    return normalize_path(cleaned)


def _looks_binary_line(line: str) -> bool:
    lower = line.lower()
    return lower.startswith("binary files ") or lower.startswith("cannot display:")
