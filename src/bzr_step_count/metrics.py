from __future__ import annotations

from datetime import datetime, timezone

from .models import AggregateBucket, FileChange, StepReport, Summary


def aggregate_changes(
    changes: list[FileChange],
    *,
    repository_path: str,
    from_revision: str,
    to_revision: str,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    config: dict | None = None,
) -> StepReport:
    counted = [change for change in changes if not change.ignored_reason and not change.is_binary]
    ignored = [change for change in changes if change.ignored_reason or change.is_binary]

    summary = Summary(
        repository_path=repository_path,
        from_revision=from_revision,
        to_revision=to_revision,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_files_changed=len(changes),
        total_files_counted=len(counted),
        total_files_ignored=len(ignored),
        total_added_lines=sum(change.added_lines for change in counted),
        total_deleted_lines=sum(change.deleted_lines for change in counted),
    )
    summary.total_changed_lines = summary.total_added_lines + summary.total_deleted_lines
    summary.total_net_lines = summary.total_added_lines - summary.total_deleted_lines

    extensions: dict[str, AggregateBucket] = {}
    directories: dict[str, AggregateBucket] = {}
    for change in counted:
        extension_key = change.extension or "(none)"
        extensions.setdefault(extension_key, AggregateBucket(extension_key)).add(change)

        directory_key = _top_directory(change.path)
        directories.setdefault(directory_key, AggregateBucket(directory_key)).add(change)

    return StepReport(
        summary=summary,
        files=changes,
        extensions=dict(sorted(extensions.items())),
        directories=dict(sorted(directories.items())),
        config=config or {},
        warnings=warnings or [],
        errors=errors or [],
    )


def _top_directory(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 and parts[0] else "."
