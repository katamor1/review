from __future__ import annotations

import re


REVISION_MANAGEMENT_IGNORED_REASON = "revision management metadata"
REVISION_MANAGEMENT_PATHS = {"meta/history-marker.txt"}
REVISION_MANAGEMENT_LINE_RE = re.compile(r"^(main_revno|side_revision)\s*=\s*\d+\s*$")


def is_revision_management_path(path: str | None) -> bool:
    if not path:
        return False
    return path.replace("\\", "/").strip("/") in REVISION_MANAGEMENT_PATHS


def is_revision_management_line(line: str) -> bool:
    return bool(REVISION_MANAGEMENT_LINE_RE.fullmatch(line.strip()))
