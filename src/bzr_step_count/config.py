from __future__ import annotations

from pathlib import Path
import json
import tomllib
from typing import Any


def load_config(path: str | None) -> dict[str, Any]:
    if not path:
        return {}

    config_path = Path(path)
    if not config_path.exists():
        raise ValueError(f"Config file does not exist: {config_path}")

    suffix = config_path.suffix.lower()
    data = config_path.read_text(encoding="utf-8")
    if suffix == ".toml":
        return tomllib.loads(data)
    if suffix == ".json":
        return json.loads(data)
    if suffix in {".yaml", ".yml"}:
        return _parse_simple_yaml(data)
    raise ValueError(f"Unsupported config file extension: {suffix}")


def _parse_simple_yaml(data: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_section: dict[str, Any] | None = None
    current_list_key: str | None = None

    for raw_line in data.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0 and stripped.endswith(":"):
            section_name = stripped[:-1]
            current_section = result.setdefault(section_name, {})
            current_list_key = None
            continue

        target = current_section if current_section is not None and indent > 0 else result
        if stripped.startswith("- ") and current_list_key:
            target[current_list_key].append(_coerce_scalar(stripped[2:].strip()))
            continue

        if ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value == "":
                target[key] = []
                current_list_key = key
            else:
                target[key] = _coerce_scalar(value)
                current_list_key = None
            continue

        raise ValueError(f"Unsupported YAML line: {raw_line}")

    return result


def _coerce_scalar(value: str) -> Any:
    cleaned = value.strip().strip('"').strip("'")
    lower = cleaned.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    try:
        return int(cleaned)
    except ValueError:
        return cleaned
