# レビュー統計サンプル

このフォルダは `scripts/generate_review_stats_samples.py` で生成したデモデータです。

## 入力例

- `review_cases/CASE-001/レビュー結果記録表.xlsx`: 注文登録機能
- `review_cases/CASE-002/レビュー結果記録表.xlsx`: 在庫引当改善
- `review_cases/CASE-003/レビュー結果記録表.xlsx`: 帳票CSV出力

各Excelには `_集計管理` シートと、外部仕様書・内部仕様書・コード・テスト仕様書の4工程シートがあります。
指摘項目には `指摘分類`, `指標対象`, `検出工程`, `原因工程` の入力例を入れています。

## 集計成果物

- `aggregate_outputs/case_summary.csv`
- `aggregate_outputs/finding_summary.csv`
- `aggregate_outputs/phase_metrics.csv`
- `aggregate_outputs/monthly_report.html`
- `aggregate_outputs/集計結果サマリー.xlsx`
- `aggregate_outputs/review_stats.sqlite`
- `aggregate_outputs/validation_errors.csv`
