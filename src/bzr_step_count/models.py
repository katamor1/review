from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Any


LANGUAGES_BY_EXTENSION = {
    ".c": "C",
    ".h": "C/C++ Header",
    ".cpp": "C++",
    ".cxx": "C++",
    ".cc": "C++",
    ".hpp": "C++ Header",
    ".java": "Java",
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".sql": "SQL",
    ".xml": "XML",
    ".properties": "Properties",
    ".md": "Markdown",
    ".json": "JSON",
    ".toml": "TOML",
    ".yaml": "YAML",
    ".yml": "YAML",
}


def normalize_path(path: str | None) -> str | None:
    if path is None:
        return None
    cleaned = path.strip().strip('"').strip("'")
    if "\t" in cleaned:
        cleaned = cleaned.split("\t", 1)[0]
    if cleaned.startswith("a/") or cleaned.startswith("b/"):
        cleaned = cleaned[2:]
    return cleaned.replace("\\", "/")


def extension_for(path: str | None) -> str:
    if not path:
        return ""
    return PurePosixPath(path).suffix.lower()


def language_for_extension(extension: str) -> str:
    return LANGUAGES_BY_EXTENSION.get(extension.lower(), "Unknown")


@dataclass
class FileChange:
    old_path: str | None = None
    new_path: str | None = None
    status: str = "unknown"
    extension: str = ""
    language: str = ""
    added_lines: int = 0
    deleted_lines: int = 0
    hunk_count: int = 0
    is_binary: bool = False
    ignored_reason: str | None = None

    def __post_init__(self) -> None:
        self.old_path = normalize_path(self.old_path)
        self.new_path = normalize_path(self.new_path)
        if self.old_path == "/dev/null":
            self.old_path = None
        if self.new_path == "/dev/null":
            self.new_path = None
        if not self.extension:
            self.extension = extension_for(self.path)
        if not self.language:
            self.language = language_for_extension(self.extension)

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or ""

    @property
    def total_changed_lines(self) -> int:
        return self.added_lines + self.deleted_lines

    @property
    def net_lines(self) -> int:
        return self.added_lines - self.deleted_lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "old_path": self.old_path,
            "new_path": self.new_path,
            "status": self.status,
            "extension": self.extension,
            "language": self.language,
            "added_lines": self.added_lines,
            "deleted_lines": self.deleted_lines,
            "total_changed_lines": self.total_changed_lines,
            "net_lines": self.net_lines,
            "hunk_count": self.hunk_count,
            "is_binary": self.is_binary,
            "ignored_reason": self.ignored_reason,
        }


@dataclass
class Summary:
    repository_path: str
    from_revision: str
    to_revision: str
    generated_at: str
    total_files_changed: int = 0
    total_files_counted: int = 0
    total_files_ignored: int = 0
    total_added_lines: int = 0
    total_deleted_lines: int = 0
    total_changed_lines: int = 0
    total_net_lines: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AggregateBucket:
    key: str
    files_changed: int = 0
    added_lines: int = 0
    deleted_lines: int = 0

    @property
    def total_changed_lines(self) -> int:
        return self.added_lines + self.deleted_lines

    @property
    def net_lines(self) -> int:
        return self.added_lines - self.deleted_lines

    def add(self, change: FileChange) -> None:
        self.files_changed += 1
        self.added_lines += change.added_lines
        self.deleted_lines += change.deleted_lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "files_changed": self.files_changed,
            "added_lines": self.added_lines,
            "deleted_lines": self.deleted_lines,
            "total_changed_lines": self.total_changed_lines,
            "net_lines": self.net_lines,
        }


@dataclass
class StepReport:
    summary: Summary
    files: list[FileChange] = field(default_factory=list)
    extensions: dict[str, AggregateBucket] = field(default_factory=dict)
    directories: dict[str, AggregateBucket] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "summary": self.summary.to_dict(),
            "files": [change.to_dict() for change in self.files],
            "extensions": {key: bucket.to_dict() for key, bucket in self.extensions.items()},
            "directories": {key: bucket.to_dict() for key, bucket in self.directories.items()},
            "config": self.config,
            "warnings": self.warnings,
            "errors": self.errors,
        }
