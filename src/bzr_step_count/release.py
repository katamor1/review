from __future__ import annotations

import sys
from collections.abc import Sequence


REVIEW_COMMANDS = frozenset({"validate", "scan", "report", "upgrade-template"})
REVIEW_PREFIXES = frozenset({"stats", "review-stats"})
STEP_PREFIXES = frozenset({"count", "bzr-step-count"})
GUI_PREFIXES = frozenset({"gui", "review-stats-gui"})
HELP_PREFIXES = frozenset({"help", "-h", "--help"})

USAGE = """review-stats.exe - レビュー統計・行数カウント統合ツール

使い方:
  review-stats.exe
  review-stats.exe gui
      GUI を起動します。ダブルクリック時もこの動作です。

  review-stats.exe scan --root <案件ルート> --output <出力先> [options]
  review-stats.exe validate --root <案件ルート> [options]
  review-stats.exe report --database <sqlite> --output <出力先>
  review-stats.exe upgrade-template --source <xlsx> --output <xlsx>
      review-stats の既存サブコマンドを実行します。
      "stats" を先頭に付けても実行できます。

  review-stats.exe count --repo <Bazaarリポジトリ> --from <rev> --to <rev> [options]
      bzr-step-count を実行します。

詳細:
  review-stats.exe stats --help
  review-stats.exe count --help
"""


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        _detach_console_for_gui()
        return _run_gui()

    mode = args[0].lower()
    remaining = args[1:]

    if mode in HELP_PREFIXES:
        print(USAGE)
        return 0

    if mode in GUI_PREFIXES:
        if remaining:
            print(f"gui モードでは追加引数を指定できません: {' '.join(remaining)}\n\n{USAGE}", file=sys.stderr)
            return 2
        _detach_console_for_gui()
        return _run_gui()

    if mode in REVIEW_PREFIXES:
        return _run_review_cli(remaining)

    if mode in REVIEW_COMMANDS:
        return _run_review_cli(args)

    if mode in STEP_PREFIXES:
        return _run_step_cli(remaining)

    print(f"不明なモードです: {args[0]}\n\n{USAGE}", file=sys.stderr)
    return 2


def _run_gui() -> int:
    from bzr_step_count.review_gui import main as gui_main

    return gui_main()


def _run_review_cli(args: list[str]) -> int:
    from bzr_step_count.review_cli import main as review_main

    return review_main(args)


def _run_step_cli(args: list[str]) -> int:
    from bzr_step_count.cli import main as step_main

    return step_main(args)


def _detach_console_for_gui() -> None:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return

    try:
        import ctypes

        ctypes.windll.kernel32.FreeConsole()
    except (AttributeError, OSError):
        # The GUI still works if the process cannot detach from its console.
        pass


if __name__ == "__main__":
    raise SystemExit(main())
