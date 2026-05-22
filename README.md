# bzr-step-count

`bzr-step-count` counts physical raw-diff step changes between two Bazaar
revisions by parsing `bzr diff -r FROM..TO` unified diff output.

```powershell
py -m pip install -e .
bzr-step-count --repo C:\path\to\repo --from 1000 --to 1100
bzr-step-count --repo . --from 1000 --to 1100 --format json --output report.json
```

The MVP counts only hunk lines: `+` as added and `-` as deleted. File headers,
Bazaar metadata, context lines, and `No newline` markers are not counted.

## review-stats

`review-stats` collects review metrics from per-case `レビュー結果記録表.xlsx`
files. It keeps Redmine out of the MVP: the workbook is the source of truth, and
Redmine issue fields are optional metadata.

```powershell
py -m pip install -e .
review-stats validate --root C:\share\案件ルート --output C:\review-stats\check
review-stats scan --root C:\share\案件ルート --output C:\review-stats\monthly
review-stats scan --root C:\share\案件ルート --output C:\review-stats\monthly --skip-bazaar
review-stats report --database C:\review-stats\monthly\review_stats.sqlite --output C:\review-stats\monthly-report
review-stats upgrade-template --source samples\レビュー結果記録表.xlsx --output samples\レビュー結果記録表_v2.xlsx
```

If the Python Scripts directory is not on `PATH`, use the module entrypoint:

```powershell
py -m bzr_step_count.review_cli scan --root C:\share\案件ルート --output C:\review-stats\monthly
```

The scan output contains:

- `review_stats.sqlite`
- `case_summary.csv`
- `finding_summary.csv`
- `phase_metrics.csv`
- `monthly_report.html`
- `validation_errors.csv`

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
- `流出不良件数`

Each review phase sheet keeps the existing `指摘項目` table, with these metric
columns added:

- `指摘分類`: `不良`, `改善`, `軽微`, `質問`, `対象外`
- `指標対象`: `対象`, `除外`
- `検出工程`
- `原因工程`

`軽微`, `質問`, and `対象外` are excluded from the standard KPI numerator.
They remain visible in report counts so review workload is still visible.

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
