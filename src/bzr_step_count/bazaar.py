from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass
class DiffCommandResult:
    stdout: str
    stderr: str
    args: list[str]


class BazaarError(RuntimeError):
    def __init__(self, kind: str, message: str, *, stderr: str = "", returncode: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.stderr = stderr
        self.returncode = returncode


def fetch_bazaar_diff(
    repository_path: str | Path,
    from_revision: str,
    to_revision: str,
    *,
    paths: list[str] | None = None,
    timeout: int | float = 60,
) -> DiffCommandResult:
    repo = Path(repository_path)
    if not repo.exists() or not repo.is_dir():
        raise BazaarError("repo_not_found", f"Repository path does not exist or is not a directory: {repo}")

    args = ["bzr", "diff", "-r", f"{from_revision}..{to_revision}"]
    args.extend(paths or [])

    try:
        completed = subprocess.run(
            args,
            cwd=str(repo),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise BazaarError("bzr_not_found", "bzr command was not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise BazaarError("timeout", f"bzr diff timed out after {timeout} seconds") from exc
    except OSError as exc:
        raise BazaarError("execution_error", str(exc)) from exc

    if completed.returncode != 0:
        message = completed.stderr.strip() or f"bzr diff failed with exit code {completed.returncode}"
        raise BazaarError("bzr_error", message, stderr=completed.stderr, returncode=completed.returncode)

    return DiffCommandResult(stdout=completed.stdout, stderr=completed.stderr, args=args)
