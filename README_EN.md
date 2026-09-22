# GA4 LTV Toolkit

GA4 LTV Toolkit calculates **observed customer lifetime value** from a GA4 BigQuery export at `user_id` grain. It runs in a standard Google Colab notebook and does not require BigQuery Notebook or BigQuery Unified API.

This release has no threshold input, prediction horizon, or manually configured customer band. It uses observed purchase and refund events.

## Documentation

- [Türkçe analiz ve yorumlama rehberi](docs/ANALYSIS_GUIDE_TR.md)
- [English analysis and interpretation guide](docs/ANALYSIS_GUIDE_EN.md)

The guides cover execution, data-quality checks, LTV distribution, P75/P90/P95, revenue concentration, Ecommerce ARPU/ARPPU/AOV, MoM and YoY comparisons, partial-month handling, basic cohort limitations, and management-ready interpretation examples.

## Inputs

```python
from ga4_ltv import LTVAnalyzer

analysis = LTVAnalyzer(
    project_id="client-project-id",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_ltv",
)
```

## Workflow

```python
analysis.validate()
analysis.dry_run()
analysis.create_base_table()
analysis.ltv_analysis()
analysis.monthly_metrics_analysis()
analysis.cohort_analysis()
dashboard_path = analysis.generate_dashboard()
```

`dry_run()` performs no write. It estimates the raw GA4 scan before the user runs the pipeline.

For a direct Colab upload without installing from GitHub, use the repository's all-in-one `ga4_ltv.py` file. It embeds the SQL templates and has no companion source-file requirement.

## Outputs

The package creates transaction, data-quality, customer, LTV distribution, monthly ecommerce KPI, MoM/YoY and basic cohort tables in the client project. It also displays notebook statistics and charts and can generate a portable, self-contained HTML report.

## Definition

Observed customer LTV is:

```text
purchase revenue − refund value
```

It is not a forecast. The cohort section is intentionally basic: it summarizes customers by first purchase month. Equal-age cumulative cohort curves are reserved for a separate cohort-analysis module.

## Monthly ecommerce KPIs

The monthly layer includes ecommerce ARPU, ARPPU, AOV, net AOV, revenue per session, purchase frequency, purchaser rate, session purchase rate, engagement, funnel-progression rates, repeat purchaser rate, new purchaser rate and refund measures. Complete months receive calendar-month MoM and same-month-prior-year YoY comparisons. Partial months remain in the table but are not promoted into comparison cards or charts.

Customer LTV uses `user_id` only. Monthly digital metrics use `user_id` when available and otherwise fall back to `user_pseudo_id`, so the monthly purchaser count can differ from the identified LTV-customer count.

## Revenue basis

The package requires no currency input. It uses local revenue when purchases contain one currency and switches to USD when multiple currencies must be compared. Both local and USD measures remain available in the output tables.

## Limitations

- Purchases without `user_id` are excluded from customer-level LTV and reported in the data-quality output.
- Results cover only the selected GA4 export tables.
- Missing or incorrect ecommerce, refund, currency or transaction ID implementation affects the result.
- This is revenue LTV, not profit LTV; product and acquisition costs are not included.
- ROAS, CPA, CAC and similar cost metrics are not calculated because the four inputs contain no advertising-cost source.
- Basic cohorts have different observation ages, so their observed LTV values are not equal-age comparisons.
- BigQuery export does not include Google Signals or behavioral modeling, so user metrics may not exactly match the GA4 interface.
- Do not place direct personal information such as email or phone numbers in `user_id`.

See [`docs/ANALYSIS_GUIDE_EN.md`](docs/ANALYSIS_GUIDE_EN.md) for the full method and interpretation guide.

Official references: [GA4 BigQuery Export schema](https://support.google.com/analytics/answer/7029846?hl=en) · [GA4 metric definitions](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema)
