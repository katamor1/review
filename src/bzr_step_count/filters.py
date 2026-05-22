from __future__ import annotations

from dataclasses import dataclass, replace
from fnmatch import fnmatch

from .models import FileChange


@dataclass
class FilterConfig:
    include_extensions: set[str] | None = None
    exclude_extensions: set[str] | None = None
    include_paths: list[str] | None = None
    exclude_paths: list[str] | None = None
    exclude_patterns: list[str] | None = None


def apply_filters(changes: list[FileChange], config: FilterConfig | None = None) -> list[FileChange]:
    if config is None:
        config = FilterConfig()

    filtered: list[FileChange] = []
    for change in changes:
        next_change = replace(change)
        next_change.ignored_reason = next_change.ignored_reason or _ignored_reason(next_change, config)
        filtered.append(next_change)
    return filtered


def _ignored_reason(change: FileChange, config: FilterConfig) -> str | None:
    path = change.path
    if change.is_binary:
        return "binary"

    if config.include_paths and not any(_path_matches_prefix(path, prefix) for prefix in config.include_paths):
        return "path not included"

    for prefix in config.exclude_paths or []:
        if _path_matches_prefix(path, prefix):
            return f"excluded by path: {prefix}"

    for pattern in config.exclude_patterns or []:
        if fnmatch(path, pattern):
            return f"excluded by pattern: {pattern}"

    extension = change.extension.lower()
    if config.include_extensions and extension not in config.include_extensions:
        return f"extension not included: {extension or '(none)'}"

    if config.exclude_extensions and extension in config.exclude_extensions:
        return f"extension excluded: {extension}"

    return None


def _path_matches_prefix(path: str, prefix: str) -> bool:
    normalized_path = path.replace("\\", "/").strip("/")
    normalized_prefix = prefix.replace("\\", "/").strip("/")
    return normalized_path == normalized_prefix or normalized_path.startswith(normalized_prefix + "/")
