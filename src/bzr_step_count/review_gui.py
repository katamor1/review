from __future__ import annotations

import json
from pathlib import Path
import queue
import threading
from typing import Any, Callable

from .models import StepReport

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover - depends on the host Python build.
    tk = None
    filedialog = None
    messagebox = None
    ttk = None

from .review_scan import (
    ReviewCaseCandidate,
    ReviewScanOptions,
    list_review_case_candidates,
    scan_review_root_with_options,
    validate_review_root_with_options,
)
from .review_models import DOCUMENT_DENSITY_UNIT_CHARACTERS, DOCUMENT_DENSITY_UNIT_PAGES, DOCUMENT_DENSITY_UNITS
from .step_count_service import count_bazaar_steps, count_folder_diff_steps
from .word_document_service import DEFAULT_CHARS_PER_PAGE, WordDocumentStats, count_word_document


DEFAULT_SETTINGS = {
    "case_root": "",
    "output_dir": "",
    "start_date": "",
    "end_date": "",
    "skip_bazaar": True,
    "document_density_unit": DOCUMENT_DENSITY_UNIT_PAGES,
    "included_workbook_paths": [],
    "excluded_workbook_paths": [],
    "bazaar_repo_path": "",
    "bazaar_from_revision": "",
    "bazaar_to_revision": "",
    "before_folder": "",
    "after_folder": "",
    "word_document_path": "",
    "word_chars_per_page": str(DEFAULT_CHARS_PER_PAGE),
}


def default_settings_path() -> Path:
    return Path.home() / ".review-stats-gui.json"


def load_gui_settings(path: str | Path | None = None) -> dict[str, Any]:
    settings_path = Path(path) if path is not None else default_settings_path()
    if not settings_path.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        loaded = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)
    if not isinstance(loaded, dict):
        return dict(DEFAULT_SETTINGS)
    settings = dict(DEFAULT_SETTINGS)
    settings.update({key: loaded.get(key, value) for key, value in DEFAULT_SETTINGS.items()})
    return settings


def save_gui_settings(path: str | Path | None, settings: dict[str, Any]) -> None:
    settings_path = Path(path) if path is not None else default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


class ReviewStatsGui:
    def __init__(self, root: Any, settings_path: str | Path | None = None) -> None:
        if tk is None or ttk is None or filedialog is None or messagebox is None:
            raise RuntimeError("tkinter が利用できません")
        self.root = root
        self.settings_path = Path(settings_path) if settings_path is not None else default_settings_path()
        self.settings = load_gui_settings(self.settings_path)
        self.candidates: list[ReviewCaseCandidate] = []
        self.selected_paths: set[str] = set(self.settings.get("included_workbook_paths") or [])
        self.excluded_paths: set[str] = set(self.settings.get("excluded_workbook_paths") or [])
        self.item_paths: dict[str, str] = {}
        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.on_worker_success: Callable[[Any], None] | None = None

        self.case_root_var = tk.StringVar(value=str(self.settings.get("case_root") or ""))
        self.output_dir_var = tk.StringVar(value=str(self.settings.get("output_dir") or ""))
        self.start_date_var = tk.StringVar(value=str(self.settings.get("start_date") or ""))
        self.end_date_var = tk.StringVar(value=str(self.settings.get("end_date") or ""))
        self.skip_bazaar_var = tk.BooleanVar(value=bool(self.settings.get("skip_bazaar", True)))
        self.document_density_unit_var = tk.StringVar(
            value=_normalize_document_density_unit_setting(self.settings.get("document_density_unit"))
        )
        self.bazaar_repo_path_var = tk.StringVar(value=str(self.settings.get("bazaar_repo_path") or ""))
        self.bazaar_from_revision_var = tk.StringVar(value=str(self.settings.get("bazaar_from_revision") or ""))
        self.bazaar_to_revision_var = tk.StringVar(value=str(self.settings.get("bazaar_to_revision") or ""))
        self.before_folder_var = tk.StringVar(value=str(self.settings.get("before_folder") or ""))
        self.after_folder_var = tk.StringVar(value=str(self.settings.get("after_folder") or ""))
        self.word_document_path_var = tk.StringVar(value=str(self.settings.get("word_document_path") or ""))
        self.word_chars_per_page_var = tk.StringVar(value=str(self.settings.get("word_chars_per_page") or DEFAULT_CHARS_PER_PAGE))

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_messages)
        if self.case_root_var.get():
            self._start_discovery()

    def _build_ui(self) -> None:
        self.root.title("review-stats-gui")
        self.root.geometry("1180x720")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        review_tab = ttk.Frame(self.notebook)
        step_tab = ttk.Frame(self.notebook)
        self.notebook.add(review_tab, text="レビュー統計")
        self.notebook.add(step_tab, text="行数カウント")
        self._build_review_stats_tab(review_tab)
        self._build_step_count_tab(step_tab)

    def _build_review_stats_tab(self, parent: Any) -> None:
        top = ttk.Frame(parent, padding=8)
        top.pack(fill=tk.X)
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="案件ルート").grid(row=0, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(top, textvariable=self.case_root_var).grid(row=0, column=1, sticky=tk.EW, pady=3)
        ttk.Button(top, text="選択", command=self._browse_case_root).grid(row=0, column=2, padx=4, pady=3)
        ttk.Button(top, text="探索", command=self._start_discovery).grid(row=0, column=3, padx=4, pady=3)

        ttk.Label(top, text="出力先").grid(row=1, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(top, textvariable=self.output_dir_var).grid(row=1, column=1, sticky=tk.EW, pady=3)
        ttk.Button(top, text="選択", command=self._browse_output_dir).grid(row=1, column=2, padx=4, pady=3)

        date_frame = ttk.Frame(top)
        date_frame.grid(row=2, column=1, sticky=tk.W, pady=3)
        ttk.Label(date_frame, text="レポート開始日").pack(side=tk.LEFT)
        ttk.Entry(date_frame, textvariable=self.start_date_var, width=14).pack(side=tk.LEFT, padx=(6, 16))
        ttk.Label(date_frame, text="レポート終了日").pack(side=tk.LEFT)
        ttk.Entry(date_frame, textvariable=self.end_date_var, width=14).pack(side=tk.LEFT, padx=(6, 16))
        ttk.Checkbutton(date_frame, text="Bazaar差分取得をスキップ", variable=self.skip_bazaar_var).pack(side=tk.LEFT)
        ttk.Label(date_frame, text="仕様書密度単位").pack(side=tk.LEFT, padx=(16, 6))
        ttk.Radiobutton(
            date_frame,
            text="ページ",
            variable=self.document_density_unit_var,
            value=DOCUMENT_DENSITY_UNIT_PAGES,
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            date_frame,
            text="1000文字",
            variable=self.document_density_unit_var,
            value=DOCUMENT_DENSITY_UNIT_CHARACTERS,
        ).pack(side=tk.LEFT, padx=(4, 0))

        action_frame = ttk.Frame(parent, padding=(8, 0, 8, 4))
        action_frame.pack(fill=tk.X)
        self.select_all_button = ttk.Button(action_frame, text="全選択", command=self._select_all)
        self.select_all_button.pack(side=tk.LEFT, padx=(0, 4))
        self.include_button = ttk.Button(action_frame, text="選択行を対象", command=lambda: self._set_selected_rows(True))
        self.include_button.pack(side=tk.LEFT, padx=4)
        self.exclude_button = ttk.Button(action_frame, text="選択行を除外", command=lambda: self._set_selected_rows(False))
        self.exclude_button.pack(side=tk.LEFT, padx=4)
        self.validate_button = ttk.Button(action_frame, text="検証", command=self._start_validation)
        self.validate_button.pack(side=tk.RIGHT, padx=4)
        self.scan_button = ttk.Button(action_frame, text="レポート生成", command=self._start_scan)
        self.scan_button.pack(side=tk.RIGHT, padx=4)

        table_frame = ttk.Frame(parent, padding=(8, 0, 8, 4))
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("target", "case_id", "case_name", "review_start", "review_end", "path", "validation_status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        headings = {
            "target": "対象",
            "case_id": "案件ID",
            "case_name": "案件名",
            "review_start": "レビュー開始日",
            "review_end": "レビュー終了日",
            "path": "パス",
            "validation_status": "検証状態",
        }
        widths = {
            "target": 70,
            "case_id": 120,
            "case_name": 180,
            "review_start": 110,
            "review_end": 110,
            "path": 420,
            "validation_status": 100,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        self.tree.bind("<Double-1>", self._toggle_clicked_row)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)

        log_frame = ttk.Frame(parent, padding=(8, 0, 8, 8))
        log_frame.pack(fill=tk.BOTH)
        ttk.Label(log_frame, text="実行ログ").pack(anchor=tk.W)
        self.log_text = tk.Text(log_frame, height=9, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _build_step_count_tab(self, parent: Any) -> None:
        top = ttk.Frame(parent, padding=8)
        top.pack(fill=tk.X)
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Bazaarリポジトリ").grid(row=0, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(top, textvariable=self.bazaar_repo_path_var).grid(row=0, column=1, sticky=tk.EW, pady=3)
        ttk.Button(top, text="選択", command=lambda: self._browse_directory(self.bazaar_repo_path_var, "Bazaarリポジトリを選択")).grid(row=0, column=2, padx=4, pady=3)

        rev_frame = ttk.Frame(top)
        rev_frame.grid(row=1, column=1, sticky=tk.W, pady=3)
        ttk.Label(rev_frame, text="from").pack(side=tk.LEFT)
        ttk.Entry(rev_frame, textvariable=self.bazaar_from_revision_var, width=16).pack(side=tk.LEFT, padx=(6, 16))
        ttk.Label(rev_frame, text="to").pack(side=tk.LEFT)
        ttk.Entry(rev_frame, textvariable=self.bazaar_to_revision_var, width=16).pack(side=tk.LEFT, padx=(6, 16))
        self.bazaar_count_button = ttk.Button(rev_frame, text="Bazaar行数カウント", command=self._start_bazaar_step_count)
        self.bazaar_count_button.pack(side=tk.LEFT)

        ttk.Label(top, text="変更前フォルダ").grid(row=2, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(top, textvariable=self.before_folder_var).grid(row=2, column=1, sticky=tk.EW, pady=3)
        ttk.Button(top, text="選択", command=lambda: self._browse_directory(self.before_folder_var, "変更前フォルダを選択")).grid(row=2, column=2, padx=4, pady=3)

        ttk.Label(top, text="変更後フォルダ").grid(row=3, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(top, textvariable=self.after_folder_var).grid(row=3, column=1, sticky=tk.EW, pady=3)
        ttk.Button(top, text="選択", command=lambda: self._browse_directory(self.after_folder_var, "変更後フォルダを選択")).grid(row=3, column=2, padx=4, pady=3)
        self.folder_count_button = ttk.Button(top, text="フォルダ比較行数カウント", command=self._start_folder_step_count)
        self.folder_count_button.grid(row=3, column=3, padx=4, pady=3)

        ttk.Label(top, text="Word文書").grid(row=4, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(top, textvariable=self.word_document_path_var).grid(row=4, column=1, sticky=tk.EW, pady=3)
        ttk.Button(top, text="選択", command=self._browse_word_document).grid(row=4, column=2, padx=4, pady=3)
        self.word_document_button = ttk.Button(top, text="Word文書ページ/文字数取得", command=self._start_word_document_count)
        self.word_document_button.grid(row=4, column=3, padx=4, pady=3)
        chars_frame = ttk.Frame(top)
        chars_frame.grid(row=5, column=1, sticky=tk.W, pady=3)
        ttk.Label(chars_frame, text="1ページあたり文字数").pack(side=tk.LEFT)
        ttk.Entry(chars_frame, textvariable=self.word_chars_per_page_var, width=10).pack(side=tk.LEFT, padx=(6, 0))

        summary = ttk.Frame(parent, padding=(8, 0, 8, 4))
        summary.pack(fill=tk.X)
        self.step_summary_vars = {
            "files_counted": tk.StringVar(value="0"),
            "files_ignored": tk.StringVar(value="0"),
            "added": tk.StringVar(value="0"),
            "deleted": tk.StringVar(value="0"),
            "total": tk.StringVar(value="0"),
            "net": tk.StringVar(value="0"),
        }
        for index, (key, label) in enumerate(
            [
                ("files_counted", "Files counted"),
                ("files_ignored", "Files ignored"),
                ("added", "Added"),
                ("deleted", "Deleted"),
                ("total", "Total"),
                ("net", "Net"),
            ]
        ):
            ttk.Label(summary, text=label).grid(row=0, column=index * 2, sticky=tk.W, padx=(0, 4))
            ttk.Label(summary, textvariable=self.step_summary_vars[key], width=10).grid(row=0, column=index * 2 + 1, sticky=tk.W, padx=(0, 12))

        word_summary = ttk.Frame(parent, padding=(8, 0, 8, 4))
        word_summary.pack(fill=tk.X)
        self.word_summary_vars = {
            "display_page_count": tk.StringVar(value=""),
            "page_count_source": tk.StringVar(value=""),
            "estimated_page_count": tk.StringVar(value=""),
            "metadata_page_count": tk.StringVar(value=""),
            "character_count_without_whitespace": tk.StringVar(value=""),
            "character_count_with_whitespace": tk.StringVar(value=""),
            "chars_per_page": tk.StringVar(value=""),
            "warnings": tk.StringVar(value=""),
        }
        for index, (key, label, width) in enumerate(
            [
                ("display_page_count", "採用ページ数", 8),
                ("page_count_source", "判定方式", 12),
                ("estimated_page_count", "推定ページ数", 8),
                ("metadata_page_count", "メタデータページ数", 10),
                ("character_count_without_whitespace", "文字数(空白除く)", 12),
                ("character_count_with_whitespace", "文字数(空白含む)", 12),
                ("chars_per_page", "1ページあたり文字数", 12),
                ("warnings", "警告", 54),
            ]
        ):
            ttk.Label(word_summary, text=label).grid(row=0, column=index * 2, sticky=tk.W, padx=(0, 4))
            ttk.Label(word_summary, textvariable=self.word_summary_vars[key], width=width).grid(
                row=0,
                column=index * 2 + 1,
                sticky=tk.W,
                padx=(0, 12),
            )

        table_frame = ttk.Frame(parent, padding=(8, 0, 8, 4))
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("path", "status", "extension", "language", "added", "deleted", "total", "net", "ignored_reason")
        self.step_tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        widths = {
            "path": 420,
            "status": 90,
            "extension": 80,
            "language": 120,
            "added": 70,
            "deleted": 70,
            "total": 70,
            "net": 70,
            "ignored_reason": 160,
        }
        for column in columns:
            self.step_tree.heading(column, text=column)
            self.step_tree.column(column, width=widths[column], anchor=tk.W)
        self.step_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.step_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.step_tree.configure(yscrollcommand=scrollbar.set)

        log_frame = ttk.Frame(parent, padding=(8, 0, 8, 8))
        log_frame.pack(fill=tk.BOTH)
        ttk.Label(log_frame, text="実行ログ").pack(anchor=tk.W)
        self.step_log_text = tk.Text(log_frame, height=7, wrap=tk.WORD)
        self.step_log_text.pack(fill=tk.BOTH, expand=True)

    def _browse_case_root(self) -> None:
        selected = filedialog.askdirectory(title="案件ルートを選択")
        if selected:
            self.case_root_var.set(selected)
            self._start_discovery()

    def _browse_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="出力先を選択")
        if selected:
            self.output_dir_var.set(selected)

    def _browse_directory(self, variable: Any, title: str) -> None:
        selected = filedialog.askdirectory(title=title)
        if selected:
            variable.set(selected)

    def _browse_word_document(self) -> None:
        selected = filedialog.askopenfilename(
            title="Word文書を選択",
            filetypes=[("Word文書", "*.docx"), ("すべてのファイル", "*.*")],
        )
        if selected:
            self.word_document_path_var.set(selected)

    def _start_discovery(self) -> None:
        root = self.case_root_var.get().strip()
        if not root:
            self._show_error("案件ルートを指定してください")
            return
        self._save_current_settings()
        self._start_worker(
            "案件探索",
            lambda: list_review_case_candidates(root),
            self._update_candidates,
        )

    def _start_validation(self) -> None:
        try:
            options = self._build_options(write_outputs=False, force_skip_bazaar=True)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self._save_current_settings()
        self._start_worker(
            "検証",
            lambda: validate_review_root_with_options(options),
            lambda dataset: self._log_dataset_summary("検証", dataset, "", bazaar_enabled=False),
        )

    def _start_scan(self) -> None:
        try:
            options = self._build_options(write_outputs=True)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self._save_current_settings()
        self._start_worker(
            "レポート生成",
            lambda: scan_review_root_with_options(options),
            lambda dataset: self._log_dataset_summary(
                "レポート生成",
                dataset,
                str(options.output_dir or ""),
                bazaar_enabled=not options.skip_bazaar,
            ),
        )

    def _start_bazaar_step_count(self) -> None:
        repo = self.bazaar_repo_path_var.get().strip()
        from_revision = self.bazaar_from_revision_var.get().strip()
        to_revision = self.bazaar_to_revision_var.get().strip()
        if not repo or not from_revision or not to_revision:
            self._show_error("Bazaarリポジトリ、from、toを指定してください")
            return
        self._save_current_settings()
        self._start_worker(
            "Bazaar行数カウント",
            lambda: count_bazaar_steps(repo, from_revision, to_revision),
            lambda report: self._update_step_count_result("Bazaar行数カウント", report),
        )

    def _start_folder_step_count(self) -> None:
        before = self.before_folder_var.get().strip()
        after = self.after_folder_var.get().strip()
        if not before or not after:
            self._show_error("変更前フォルダと変更後フォルダを指定してください")
            return
        self._save_current_settings()
        self._start_worker(
            "フォルダ比較行数カウント",
            lambda: count_folder_diff_steps(before, after),
            lambda report: self._update_step_count_result("フォルダ比較行数カウント", report),
        )

    def _start_word_document_count(self) -> None:
        path = self.word_document_path_var.get().strip()
        if not path:
            self._show_error("Word文書を指定してください")
            return
        try:
            chars_per_page = int(self.word_chars_per_page_var.get().strip())
        except ValueError:
            self._show_error("1ページあたり文字数は整数で指定してください")
            return
        if chars_per_page <= 0:
            self._show_error("1ページあたり文字数は1以上を指定してください")
            return
        self._save_current_settings()
        self._start_worker(
            "Word文書ページ/文字数取得",
            lambda: count_word_document(path, chars_per_page=chars_per_page),
            lambda stats: self._update_word_document_result("Word文書ページ/文字数取得", stats),
        )

    def _start_worker(self, label: str, target: Callable[[], Any], on_success: Callable[[Any], None]) -> None:
        if self.worker and self.worker.is_alive():
            self._show_error("処理が実行中です")
            return
        self.on_worker_success = on_success
        self._set_running(True)
        self._post_log(f"{label}を開始しました")

        def run() -> None:
            try:
                result = target()
            except Exception as exc:  # pragma: no cover - exercised manually through the GUI.
                self.messages.put(("error", f"{label}に失敗しました: {exc}"))
            else:
                self.messages.put(("success", (label, result)))

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def _poll_messages(self) -> None:
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "error":
                self._append_log(str(payload))
                self._set_running(False)
                messagebox.showerror("review-stats-gui", str(payload))
            elif kind == "success":
                label, result = payload
                self._append_log(f"{label}が完了しました")
                if self.on_worker_success:
                    self.on_worker_success(result)
                self._set_running(False)
        self.root.after(100, self._poll_messages)

    def _update_candidates(self, candidates: list[ReviewCaseCandidate]) -> None:
        self.candidates = candidates
        saved_included = set(self.settings.get("included_workbook_paths") or [])
        saved_excluded = set(self.settings.get("excluded_workbook_paths") or [])
        self.tree.delete(*self.tree.get_children())
        self.item_paths.clear()
        if saved_included:
            self.selected_paths = set(saved_included)
        else:
            self.selected_paths = {candidate.path for candidate in candidates if candidate.path not in saved_excluded}
        self.excluded_paths = {candidate.path for candidate in candidates if candidate.path not in self.selected_paths}
        for index, candidate in enumerate(candidates):
            item_id = f"case-{index}"
            self.item_paths[item_id] = candidate.path
            self.tree.insert(
                "",
                tk.END,
                iid=item_id,
                values=(
                    self._target_label(candidate.path),
                    candidate.case_id,
                    candidate.case_name,
                    candidate.review_start,
                    candidate.review_end,
                    candidate.path,
                    candidate.validation_status,
                ),
            )
        self._post_log(f"レビュー結果記録表.xlsx を {len(candidates)} 件見つけました")

    def _select_all(self) -> None:
        self.selected_paths = {candidate.path for candidate in self.candidates}
        self.excluded_paths = set()
        self._refresh_target_labels()

    def _set_selected_rows(self, selected: bool) -> None:
        for item_id in self.tree.selection():
            path = self.item_paths.get(item_id)
            if not path:
                continue
            if selected:
                self.selected_paths.add(path)
                self.excluded_paths.discard(path)
            else:
                self.selected_paths.discard(path)
                self.excluded_paths.add(path)
        self._refresh_target_labels()

    def _toggle_clicked_row(self, _event: Any) -> None:
        self._set_selected_rows(False if any(self.item_paths.get(item) in self.selected_paths for item in self.tree.selection()) else True)

    def _refresh_target_labels(self) -> None:
        for item_id, path in self.item_paths.items():
            values = list(self.tree.item(item_id, "values"))
            values[0] = self._target_label(path)
            self.tree.item(item_id, values=values)

    def _target_label(self, path: str) -> str:
        return "対象" if path in self.selected_paths else "除外"

    def _build_options(self, *, write_outputs: bool, force_skip_bazaar: bool = False) -> ReviewScanOptions:
        root = self.case_root_var.get().strip()
        if not root:
            raise ValueError("案件ルートを指定してください")
        output_dir = self.output_dir_var.get().strip()
        if write_outputs and not output_dir:
            raise ValueError("出力先を指定してください")
        included_paths = tuple(candidate.path for candidate in self.candidates if candidate.path in self.selected_paths)
        return ReviewScanOptions(
            root=root,
            output_dir=output_dir or None,
            start_date=self.start_date_var.get().strip() or None,
            end_date=self.end_date_var.get().strip() or None,
            included_workbook_paths=included_paths if self.candidates else None,
            excluded_workbook_paths=tuple(sorted(self.excluded_paths)),
            skip_bazaar=True if force_skip_bazaar else bool(self.skip_bazaar_var.get()),
            document_density_unit=_normalize_document_density_unit_setting(self.document_density_unit_var.get()),
            write_outputs=write_outputs,
        )

    def _collect_settings(self) -> dict[str, Any]:
        return {
            "case_root": self.case_root_var.get().strip(),
            "output_dir": self.output_dir_var.get().strip(),
            "start_date": self.start_date_var.get().strip(),
            "end_date": self.end_date_var.get().strip(),
            "skip_bazaar": bool(self.skip_bazaar_var.get()),
            "document_density_unit": _normalize_document_density_unit_setting(self.document_density_unit_var.get()),
            "included_workbook_paths": sorted(self.selected_paths),
            "excluded_workbook_paths": sorted(self.excluded_paths),
            "bazaar_repo_path": self.bazaar_repo_path_var.get().strip(),
            "bazaar_from_revision": self.bazaar_from_revision_var.get().strip(),
            "bazaar_to_revision": self.bazaar_to_revision_var.get().strip(),
            "before_folder": self.before_folder_var.get().strip(),
            "after_folder": self.after_folder_var.get().strip(),
            "word_document_path": self.word_document_path_var.get().strip(),
            "word_chars_per_page": self.word_chars_per_page_var.get().strip(),
        }

    def _save_current_settings(self) -> None:
        save_gui_settings(self.settings_path, self._collect_settings())

    def _log_dataset_summary(self, label: str, dataset: Any, output_dir: str, *, bazaar_enabled: bool = False) -> None:
        error_count = sum(1 for error in dataset.validation_errors if error.severity == "error")
        warning_count = sum(1 for error in dataset.validation_errors if error.severity == "warning")
        self._post_log(f"{label}: 案件 {len(dataset.cases)} 件 / 指摘 {len(dataset.findings)} 件")
        self._post_log(f"{label}: error {error_count} 件 / warning {warning_count} 件")
        self._post_log(f"{label}: 仕様書指摘密度単位 {_document_density_unit_label(self.document_density_unit_var.get())}")
        for line in format_bazaar_diff_log_lines(dataset, bazaar_enabled=bazaar_enabled):
            self._post_log(line)
        if output_dir:
            self._post_log(f"{label}: 出力先 {output_dir}")

    def _update_step_count_result(self, label: str, report: StepReport) -> None:
        summary, rows = format_step_report_for_gui(report)
        for key, value in summary.items():
            if key in self.step_summary_vars:
                self.step_summary_vars[key].set(f"{value:,}" if isinstance(value, int) else str(value))
        self.step_tree.delete(*self.step_tree.get_children())
        for row in rows:
            self.step_tree.insert(
                "",
                tk.END,
                values=(
                    row["path"],
                    row["status"],
                    row["extension"],
                    row["language"],
                    row["added"],
                    row["deleted"],
                    row["total"],
                    row["net"],
                    row["ignored_reason"],
                ),
            )
        self._post_log(
            f"{label}: files counted {summary['files_counted']} / ignored {summary['files_ignored']} / total {summary['total']}"
        )
        for warning in report.warnings:
            self._post_log(f"{label} warning: {warning}")
        for error in report.errors:
            self._post_log(f"{label} error: {error}")

    def _update_word_document_result(self, label: str, stats: WordDocumentStats) -> None:
        summary = format_word_document_stats_for_gui(stats)
        for key, value in summary.items():
            if key in self.word_summary_vars:
                self.word_summary_vars[key].set(value)
        self._post_log(
            f"{label}: 採用ページ数 {summary['display_page_count'] or '未取得'} / "
            f"判定方式 {summary['page_count_source']} / "
            f"文字数(空白除く) {summary['character_count_without_whitespace']} / "
            f"文字数(空白含む) {summary['character_count_with_whitespace']}"
        )
        for warning in stats.warnings:
            self._post_log(f"{label} warning: {warning}")

    def _post_log(self, message: str) -> None:
        self.messages.put(("log", message))

    def _append_log(self, message: str) -> None:
        for widget_name in ["log_text", "step_log_text"]:
            widget = getattr(self, widget_name, None)
            if widget is None:
                continue
            widget.insert(tk.END, message + "\n")
            widget.see(tk.END)

    def _set_running(self, running: bool) -> None:
        state = tk.DISABLED if running else tk.NORMAL
        for button in [
            self.select_all_button,
            self.include_button,
            self.exclude_button,
            self.validate_button,
            self.scan_button,
            getattr(self, "bazaar_count_button", None),
            getattr(self, "folder_count_button", None),
            getattr(self, "word_document_button", None),
        ]:
            if button is not None:
                button.configure(state=state)

    def _show_error(self, message: str) -> None:
        self._append_log(message)
        messagebox.showerror("review-stats-gui", message)

    def _on_close(self) -> None:
        self._save_current_settings()
        self.root.destroy()


def format_step_report_for_gui(report: StepReport) -> tuple[dict[str, int], list[dict[str, Any]]]:
    summary = report.summary
    rows = [
        {
            "path": change.path,
            "status": change.status,
            "extension": change.extension,
            "language": change.language,
            "added": change.added_lines,
            "deleted": change.deleted_lines,
            "total": change.total_changed_lines,
            "net": change.net_lines,
            "ignored_reason": change.ignored_reason or "",
        }
        for change in report.files
    ]
    return (
        {
            "files_counted": summary.total_files_counted,
            "files_ignored": summary.total_files_ignored,
            "added": summary.total_added_lines,
            "deleted": summary.total_deleted_lines,
            "total": summary.total_changed_lines,
            "net": summary.total_net_lines,
        },
        rows,
    )


def format_word_document_stats_for_gui(stats: WordDocumentStats) -> dict[str, str]:
    return {
        "display_page_count": "" if stats.display_page_count is None else f"{stats.display_page_count:,}",
        "page_count_source": stats.page_count_source,
        "estimated_page_count": "" if stats.estimated_page_count is None else f"{stats.estimated_page_count:,}",
        "metadata_page_count": "" if stats.metadata_page_count is None else f"{stats.metadata_page_count:,}",
        "character_count_without_whitespace": f"{stats.character_count_without_whitespace:,}",
        "character_count_with_whitespace": f"{stats.character_count_with_whitespace:,}",
        "chars_per_page": f"{stats.chars_per_page:,}",
        "warnings": "; ".join(stats.warnings),
    }


def format_bazaar_diff_log_lines(dataset: Any, *, bazaar_enabled: bool) -> list[str]:
    if not bazaar_enabled:
        return []

    lines: list[str] = []
    failures = {
        error.case_id: error.message
        for error in getattr(dataset, "validation_errors", [])
        if getattr(error, "code", "") == "bazaar_diff_failed"
    }
    seen_case_ids: set[str] = set()
    for case in getattr(dataset, "cases", []):
        metadata = case.metadata
        case_id = metadata.case_id or "(案件ID未設定)"
        seen_case_ids.add(case_id)
        detected = metadata.bazaar_detected_changed_lines
        if detected is not None:
            lines.append(
                f"Bazaar差分: {case_id} {metadata.from_revision}..{metadata.to_revision} "
                f"検出差分行数 {_format_count(detected)} 行"
            )
            continue
        if case_id in failures:
            lines.append(f"Bazaar差分: {case_id} 取得失敗: {failures[case_id]}")
            continue
        has_bazaar_range = bool(metadata.bazaar_repo_path and metadata.from_revision and metadata.to_revision)
        if has_bazaar_range and metadata.code_changed_lines > 0:
            lines.append(
                f"Bazaar差分: {case_id} 取得省略 "
                f"(Excelのコード変更ステップ数 {_format_count(metadata.code_changed_lines)} 行を使用)"
            )
        elif not has_bazaar_range:
            lines.append(f"Bazaar差分: {case_id} 取得なし (Bazaarリポジトリパス/from/toリビジョン未入力)")
    for case_id, message in failures.items():
        if case_id not in seen_case_ids:
            lines.append(f"Bazaar差分: {case_id or '(案件ID未設定)'} 取得失敗: {message}")
    return lines


def _format_count(value: float | int) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return f"{int(numeric):,}"
    return f"{numeric:,.2f}"


def _normalize_document_density_unit_setting(value: Any) -> str:
    unit = str(value or DOCUMENT_DENSITY_UNIT_PAGES).strip().lower()
    if unit not in DOCUMENT_DENSITY_UNITS:
        return DOCUMENT_DENSITY_UNIT_PAGES
    return unit


def _document_density_unit_label(value: str) -> str:
    return "1000文字" if _normalize_document_density_unit_setting(value) == DOCUMENT_DENSITY_UNIT_CHARACTERS else "ページ"


def main() -> int:
    if tk is None:
        print("tkinter が利用できません")
        return 1
    root = tk.Tk()
    ReviewStatsGui(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
