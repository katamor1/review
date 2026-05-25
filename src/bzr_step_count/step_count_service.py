from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path

from .bazaar import fetch_bazaar_diff
from .metrics import aggregate_changes
from .models import FileChange, StepReport
from .parser import parse_unified_diff
from .revision_metadata import REVISION_MANAGEMENT_IGNORED_REASON, is_revision_management_path


TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp932")


def count_bazaar_steps(
    repository_path: str | Path,
    from_revision: str,
    to_revision: str,
    *,
    timeout: int | float = 60,
) -> StepReport:
    diff = fetch_bazaar_diff(repository_path, from_revision, to_revision, timeout=timeout)
    parse_result = parse_unified_diff(diff.stdout)
    return aggregate_changes(
        parse_result.files,
        repository_path=str(Path(repository_path)),
        from_revision=str(from_revision),
        to_revision=str(to_revision),
        warnings=parse_result.warnings,
        errors=parse_result.errors,
    )


def count_folder_diff_steps(before_folder: str | Path, after_folder: str | Path) -> StepReport:
    before_root = Path(before_folder)
    after_root = Path(after_folder)
    if not before_root.exists() or not before_root.is_dir():
        raise ValueError(f"変更前フォルダが見つかりません: {before_root}")
    if not after_root.exists() or not after_root.is_dir():
        raise ValueError(f"変更後フォルダが見つかりません: {after_root}")

    before_files = _collect_files(before_root)
    after_files = _collect_files(after_root)
    changes: list[FileChange] = []
    warnings: list[str] = []

    for relative_path in sorted(set(before_files) | set(after_files)):
        before_path = before_files.get(relative_path)
        after_path = after_files.get(relative_path)
        change, warning = _compare_file(relative_path, before_path, after_path)
        changes.append(change)
        if warning:
            warnings.append(warning)

    return aggregate_changes(
        changes,
        repository_path=f"{before_root} -> {after_root}",
        from_revision=str(before_root),
        to_revision=str(after_root),
        warnings=warnings,
    )


def _collect_files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
    }


def _compare_file(relative_path: str, before_path: Path | None, after_path: Path | None) -> tuple[FileChange, str | None]:
    if is_revision_management_path(relative_path):
        return (
            FileChange(
                old_path=relative_path if before_path else None,
                new_path=relative_path if after_path else None,
                status="metadata",
                ignored_reason=REVISION_MANAGEMENT_IGNORED_REASON,
            ),
            None,
        )

    before_lines, before_binary = _read_text_lines(before_path) if before_path else ([], False)
    after_lines, after_binary = _read_text_lines(after_path) if after_path else ([], False)
    if before_binary or after_binary:
        change = FileChange(
            old_path=relative_path if before_path else None,
            new_path=relative_path if after_path else None,
            status="binary",
            is_binary=True,
            ignored_reason="binary",
        )
        return change, f"Binary file skipped for {relative_path}"

    if before_path is None:
        return FileChange(new_path=relative_path, status="added", added_lines=len(after_lines), hunk_count=1), None
    if after_path is None:
        return FileChange(old_path=relative_path, status="removed", deleted_lines=len(before_lines), hunk_count=1), None
    added, deleted, hunk_count = _diff_line_counts(before_lines, after_lines)
    status = "unchanged" if added == 0 and deleted == 0 else "modified"
    return FileChange(
        old_path=relative_path,
        new_path=relative_path,
        status=status,
        added_lines=added,
        deleted_lines=deleted,
        hunk_count=hunk_count,
    ), None


def _read_text_lines(path: Path | None) -> tuple[list[str], bool]:
    if path is None:
        return [], False
    data = path.read_bytes()
    if b"\x00" in data:
        return [], True
    for encoding in TEXT_ENCODINGS:
        try:
            return data.decode(encoding).splitlines(), False
        except UnicodeDecodeError:
            continue
    return [], True


def _diff_line_counts(before_lines: list[str], after_lines: list[str]) -> tuple[int, int, int]:
    added = 0
    deleted = 0
    hunk_count = 0
    for tag, before_start, before_end, after_start, after_end in SequenceMatcher(
        None,
        before_lines,
        after_lines,
        autojunk=False,
    ).get_opcodes():
        if tag == "equal":
            continue
        hunk_count += 1
        if tag in {"replace", "delete"}:
            deleted += before_end - before_start
        if tag in {"replace", "insert"}:
            added += after_end - after_start
    return added, deleted, hunk_count
