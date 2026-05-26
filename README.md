# bzr-step-count

`bzr-step-count` counts physical raw-diff step changes between two Bazaar
revisions by parsing `bzr diff -r FROM..TO` unified diff output.
It invokes Bazaar with `--no-aliases` so GUI-oriented `diff` aliases, such as
WinMerge launchers used by Bazaar Explorer/QBzr, do not replace the unified diff
text needed for line counting.

```powershell
py -m pip install -e .
bzr-step-count --repo C:\path\to\repo --from 1000 --to 1100
bzr-step-count --repo . --from 1000 --to 1100 --format json --output report.json
```

The MVP counts only hunk lines: `+` as added and `-` as deleted. File headers,
Bazaar metadata, context lines, and `No newline` markers are not counted.
Known generated revision-management metadata such as `meta/history-marker.txt`
and `main_revno` / `side_revision` hunk lines are excluded from counted lines.

## review-stats

`review-stats` collects review metrics from per-case `レビュー結果記録表.xlsx`
files. It keeps Redmine out of the MVP: the workbook is the source of truth, and
Redmine issue fields are optional metadata.

```powershell
py -m pip install -e .
review-stats validate --root C:\share\案件ルート --output C:\review-stats\check
review-stats scan --root C:\share\案件ルート --output C:\review-stats\monthly
review-stats scan --root C:\share\案件ルート --output C:\review-stats\monthly --skip-bazaar
review-stats scan --root C:\share\案件ルート --output C:\review-stats\monthly --document-density-unit characters
review-stats report --database C:\review-stats\monthly\review_stats.sqlite --output C:\review-stats\monthly-report
review-stats upgrade-template --source samples\レビュー結果記録表.xlsx --output samples\レビュー結果記録表_v2.xlsx
review-stats-gui
```

If the Python Scripts directory is not on `PATH`, use the module entrypoint:

```powershell
py -m bzr_step_count.review_cli scan --root C:\share\案件ルート --output C:\review-stats\monthly
```

The GUI entrypoint is a thin tkinter wrapper around the same scan code. It can
select the case root, output directory, report period, target workbooks, and the
Bazaar skip flag. It can also switch the specification-document density
denominator between page count and `1,000` characters. It saves the last-used settings to
`%USERPROFILE%\.review-stats-gui.json`.
When `Bazaar差分取得をスキップ` is unchecked during report generation, the
execution log shows the detected Bazaar changed-line count per case. If a case
already has `コード変更ステップ数` in Excel, that Excel value is used and the
log records that Bazaar retrieval was skipped for that case.

The GUI has two tabs. `レビュー統計` runs the workbook validation/report flow.
`行数カウント` runs standalone line counting for either a Bazaar revision range
or a before/after folder pair. Folder comparison reports added/deleted/total/net
diff lines by relative path; it does not infer renames. The same tab can also
read a `.docx` Word document and display adopted page count, character counts
with and without whitespace, estimated page count, and DOCX metadata page count.
If LibreOffice `soffice` is available on `PATH`, the tool converts the document
to PDF and adopts the rendered PDF page count. If PDF conversion is unavailable
or fails, it adopts an estimated page count based on `文字数(空白除く) /
1ページあたり文字数`; the GUI default is `1400`. The DOCX metadata value
(`docProps/app.xml` `Pages`) is shown only as a reference because it can be stale
when a document was edited by a tool that did not recalculate and save metadata.

The scan output contains:

- `review_stats.sqlite`
- `case_summary.csv`
- `finding_summary.csv`
- `phase_metrics.csv`
- `cross_summary.csv`
- `phase_summary.csv`
- `owner_summary.csv`
- `reviewer_summary.csv`
- `monthly_report.html`
- `validation_errors.csv`

`phase_metrics.csv` and the HTML report include `指摘密度単位`, such as
`件/KLOC` for code and `件/ページ` or `件/1000文字` for document review phases.
The default document density unit is pages. Use
`--document-density-unit characters` or the GUI `仕様書密度単位` control to make
the main document density use `_集計管理` sheet character-count keys
(`外部仕様書文字数`, `内部仕様書文字数`, `テスト仕様書文字数`) as the denominator.

### Workbook contract

Add a `_集計管理` sheet with two columns: `項目`, `値`.

Required or recommended keys:

- `案件ID`
- `案件名`
- `Bazaarリポジトリパス`
- `コードfromリビジョン`
- `コードtoリビジョン`
- `コード変更ステップ数`
- `外部仕様書ページ数`
- `内部仕様書ページ数`
- `テスト仕様書ページ数`
- `外部仕様書文字数`
- `内部仕様書文字数`
- `テスト仕様書文字数`
- `流出不良件数`: `リリース後` シートの指標対象不良から算出する表示用項目

The scan target phase sheets are `外部仕様書`, `内部仕様書`, `コード`,
`テスト仕様書`, and `リリース後`. `後工程` remains a legacy alias for
`リリース後`. Existing workbooks without a `リリース後` sheet are still readable;
the scanner emits a warning and treats escaped defects as empty.

Each review phase sheet keeps the existing `指摘項目` table, with these metric
columns added:

- `指摘分類`: `不良`, `改善`, `軽微`, `質問`, `対象外`
- `指標対象`: `対象`, `除外`
- `検出工程`
- `原因工程`

`軽微`, `質問`, and `対象外` are excluded from the standard KPI numerator.
They remain visible in report counts so review workload is still visible.
Python does not rely on Excel formula recalculation for escaped defects; it
recomputes `流出不良件数` from the `リリース後` sheet during scan.

### Docker use on the shared PC

The file server is mounted read-only into the container. Because the current
operation requires manual login to access the share, run the batch after the
share is visible on the shared PC.

```powershell
$env:REVIEW_CASE_ROOT="X:\案件ルート"
$env:REVIEW_OUTPUT_ROOT="C:\review-stats\monthly"
docker compose run --rm review-stats scan --root /cases --output /outputs
```

If WSL2/Docker cannot see the file-server mount, run the same CLI directly on
the shared PC host with `py -m pip install -e .`.
