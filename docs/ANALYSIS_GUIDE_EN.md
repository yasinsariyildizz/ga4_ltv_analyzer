# GA4 LTV Toolkit — Analysis & Interpretation Guide

This document explains the methodology, outputs, charts, and interpretation rules used by `ga4-ltv-toolkit`.

The toolkit is designed to answer four practical questions:

- How much net purchase revenue have identified customers generated in the selected GA4 history?
- How widely is customer value distributed?
- How are monthly ecommerce efficiency and conversion metrics changing?
- What does a basic first-purchase-month cohort view show?

The toolkit calculates **observed revenue LTV**. It does not forecast future LTV.

---

# 1. Core definition

For each identified customer:

```text
Observed LTV = total purchase revenue − total refund value
```

Example:

```text
Purchase 1                  TRY 900
Purchase 2                  TRY 600
Refund                      TRY 200
-----------------------------------
Observed LTV              TRY 1,300
```

“Lifetime” means the period visible in the selected GA4 export history. Purchases before or after that history are not included.

---

# 2. What the analysis is not

The output is not:

- a future 6- or 12-month LTV forecast,
- profit LTV,
- customer acquisition cost analysis,
- campaign incrementality measurement,
- a detailed retention matrix,
- an automatic customer-quality classification.

Product cost, shipping, commission, media spend, and service cost are absent. The result must therefore be described as **revenue LTV**, not profit.

---

# 3. Customer identity scope

Customer-level LTV uses **GA4 `user_id`**.

`user_pseudo_id` is mainly a browser or device identifier. One person can appear under multiple pseudo IDs. A correctly implemented `user_id` can connect authenticated activity across devices.

Only purchases with a populated `user_id` enter customer LTV. The data-quality table reports the excluded volume and the coverage rate:

```text
user_id coverage = purchases with user_id / all purchase events
```

If coverage is 65%, the customer analysis represents the identified portion of purchasing activity, not the entire purchaser population.

---

# 4. Monthly user scope

Monthly digital and ecommerce metrics need broader traffic coverage. They use:

```text
user_id when available; otherwise user_pseudo_id
```

The monthly purchaser count can therefore differ from the customer count in `ltv_customer_summary`.

Google Signals and modeled behavior are not present in the BigQuery export. User counts may consequently differ from the GA4 interface.

---

# 5. Required GA4 implementation

The main required fields are:

- `user_id` and `user_pseudo_id`,
- event date and timestamp,
- `ecommerce.transaction_id`,
- purchase and refund revenue fields,
- currency,
- total item quantity,
- `ga_session_id`,
- `session_engaged`.

Monthly funnel metrics also depend on correctly implemented standard events:

```text
view_item
add_to_cart
begin_checkout
purchase
refund
```

Missing event stages make the corresponding progression rates incomplete.

---

# 6. Inputs

The analyzer intentionally requires only four inputs:

```python
analysis = LTVAnalyzer(
    project_id="client-project-id",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_ltv",
)
```

There is no threshold, prediction horizon, customer band, or currency input.

---

# 7. Recommended workflow

```python
analysis.validate()
analysis.dry_run()
analysis.create_base_table()
analysis.ltv_analysis()
analysis.monthly_metrics_analysis()
analysis.cohort_analysis()
dashboard_path = analysis.generate_dashboard()
```

The steps should be run in this order because later outputs depend on earlier tables.

`analysis.run_all()` runs the complete workflow, but step-by-step execution is recommended for the first run so that scan estimates and data-quality results can be reviewed before interpretation.

---

# 8. `validate()`

`validate()` checks:

- access to the source dataset,
- whether the table pattern matches source tables,
- dataset location,
- output dataset name.

It does not write analysis tables.

An unexpectedly small table count can indicate an incorrect dataset or table pattern.

---

# 9. `dry_run()`

`dry_run()` estimates source bytes without writing data.

Two raw GA4 scans are estimated:

1. purchase/refund transaction preparation,
2. monthly digital and ecommerce metrics.

The remaining analysis steps read the smaller output tables.

Run `dry_run()` again whenever the source project, dataset, table pattern, or included date history changes.

---

# 10. Transaction base and deduplication

`create_base_table()` creates:

```text
ltv_transaction_base
ltv_data_quality
```

The transaction-base grain is one deduplicated `purchase` or `refund` event.

Daily `events_YYYYMMDD` tables are used. `events_intraday_*` tables are excluded to avoid overlap.

Purchases with a transaction ID are deduplicated using the event type, user key, and transaction ID. When transaction ID is missing, timestamp and bundle sequence fields provide a technical fallback. This fallback is less reliable than a properly implemented transaction ID.

Refund keys also include timestamp and value so that legitimate partial refunds are not collapsed into one row.

---

# 11. Data-quality output

`ltv_data_quality` reports:

- purchase and refund event counts,
- purchases eligible for customer LTV,
- purchases missing `user_id`,
- purchases missing transaction ID,
- purchases missing revenue,
- local and USD value coverage,
- observed currencies,
- `user_id`, transaction ID, and revenue coverage rates.

Example:

```text
user_id coverage          81%
transaction ID coverage  98%
revenue coverage         99%
```

This indicates strong transaction and revenue tracking, while customer LTV still represents approximately 81% of purchases.

---

# 12. `ltv_analysis()` outputs

The method creates:

```text
ltv_customer_summary
ltv_overall_summary
ltv_decile_summary
ltv_percentile_distribution
```

It also displays summary cards, distribution charts, and interpretation notes in the notebook.

---

# 13. Customer summary grain

Each row in `ltv_customer_summary` represents one `user_id` with at least one purchase.

The table contains:

- first and last purchase dates,
- order and refund-event counts,
- repeat-customer flag,
- purchase span,
- observed days since first purchase,
- days since last purchase,
- gross, refund, and net revenue,
- customer-level AOV.

`repeat_customer = TRUE` means the customer has at least two observed purchase events in the selected history.

The analysis end date is the latest commerce-event date in the transaction base. It can be earlier than the latest raw GA4 event date when no purchase or refund occurred near the source period end.

---

# 14. Mean and median LTV

Mean LTV is:

```text
total net revenue / identified purchasing customers
```

Median LTV is the middle customer value after sorting the population.

Example:

```text
Mean LTV     TRY 2,450
Median LTV     TRY 820
```

The large difference suggests that a relatively small number of high-value customers lift the mean. Median is usually a better description of a typical customer, while mean remains useful for total economic contribution.

Both should be reported together.

---

# 15. P75, P90, and P95

Percentiles describe the upper part of the customer-value distribution.

```text
P75: 75% of customers are at or below this LTV
P90: 90% are at or below this LTV
P95: 95% are at or below this LTV
```

A large gap between P90 and P95 indicates a long upper tail and a very high-value top group.

Percentiles are descriptive. They are not automatic campaign thresholds.

---

# 16. Negative LTV

A negative observed LTV means that attributed refund value exceeds attributed purchase revenue in the selected history.

Possible explanations include:

- a purchase occurred before the selected period but its refund occurred inside it,
- purchase and refund identity fields differ,
- duplicate refunds,
- missing purchase revenue,
- a genuine correction larger than observed purchases.

Negative-LTV customers should be investigated before being labeled unprofitable.

---

# 17. LTV deciles

Customers are sorted by net revenue from highest to lowest and divided into ten approximately equal groups:

```text
D1  = highest-LTV approximate top 10%
D10 = lowest-LTV approximate bottom 10%
```

Each decile reports customer count, orders, total and average net revenue, minimum and maximum LTV, repeat rate, positive revenue share, and cumulative shares.

Decile sizes can differ slightly when the customer count is not divisible by ten.

---

# 18. Revenue concentration

The concentration curve starts with the highest-LTV customers and shows cumulative positive net revenue.

Example:

```text
Top 10% of customers → 44% of positive net revenue
Top 20% of customers → 63% of positive net revenue
```

This indicates strong concentration and possible dependency on a small high-value group.

Negative LTV is set to zero for concentration-share calculations so that negative refunds do not distort the distribution of positive revenue.

---

# 19. Repeat behavior

Customer-level repeat rate is:

```text
customers with at least two orders / all identified purchasing customers
```

Orders per customer is:

```text
total orders / identified purchasing customers
```

These metrics should be interpreted with the natural purchase cycle. A low repeat rate can be expected for annual or infrequent categories and problematic for fast-repeat categories.

---

# 20. Monthly ecommerce layer

`monthly_metrics_analysis()` creates:

```text
ltv_monthly_metrics
ltv_monthly_metric_changes
```

The first table has one row per calendar month. The second has one row per month and metric.

The notebook displays the latest complete month, monthly trend charts, and MoM/YoY comparisons.

---

# 21. Core monthly metrics

| Metric | Definition |
| --- | --- |
| Gross purchase revenue | Sum of deduplicated purchase revenue |
| Net purchase revenue | Gross revenue minus refund value |
| Orders | Deduplicated purchase events |
| Purchasers | Users with at least one purchase in the month |
| Purchase frequency | Orders divided by purchasers |
| Items per order | Purchased item quantity divided by orders |
| Monthly repeat purchaser rate | Purchasers with at least two monthly orders divided by purchasers |
| New purchaser rate | First observed purchasers in selected history divided by monthly purchasers |

“New purchaser” means new within the selected export history. If history begins late, an existing customer can appear new in the first observed month.

---

# 22. Ecommerce ARPU, ARPPU, and AOV

The toolkit uses these explicit definitions:

```text
Ecommerce ARPU  = net purchase revenue / active users
Ecommerce ARPPU = net purchase revenue / purchasers
AOV             = gross purchase revenue / orders
Net AOV         = net purchase revenue / orders
```

Example:

```text
Active users                 10,000
Purchasers                      800
Orders                        1,000
Gross purchase revenue  TRY 1,300,000
Refund value            TRY   100,000
Net purchase revenue    TRY 1,200,000
```

Results:

```text
Ecommerce ARPU       TRY   120
Ecommerce ARPPU      TRY 1,500
AOV                   TRY 1,300
Net AOV               TRY 1,200
```

The toolkit's Ecommerce ARPU is not identical to a GA4 ARPU based on total revenue. It intentionally uses net purchase revenue only.

---

# 23. Reading ARPU and ARPPU together

## ARPU rises while ARPPU is stable

A larger share of active users may be converting, while revenue per purchaser remains stable.

## ARPU is stable while ARPPU rises

Purchaser value may be increasing while purchaser rate decreases.

## Both decline

Review AOV, purchase frequency, purchaser rate, and refunds together.

ARPU movement alone does not establish campaign impact.

---

# 24. Session and engagement metrics

```text
Engagement rate = engaged sessions / sessions
Bounce rate = 1 − engagement rate
Sessions per active user = sessions / active users
Events per active user = events / active users
Revenue per session = net purchase revenue / sessions
```

A session key combines `user_pseudo_id` and `ga_session_id`. Events missing either field cannot enter the session count.

An increase in engagement with a decline in revenue per session can mean content consumption improved without a matching increase in commercial efficiency.

---

# 25. Conversion and funnel-progression metrics

The monthly table includes:

```text
Purchaser rate = purchasers / active users
Session purchase rate = purchase sessions / sessions
View-to-cart user rate = add_to_cart users / view_item users
Cart-to-checkout user rate = begin_checkout users / add_to_cart users
Checkout-to-purchase user rate = purchase users / begin_checkout users
View-to-purchase user rate = purchase users / view_item users
```

These metrics compare unique users within the same calendar month. They are not a strict ordered, same-session closed funnel.

A user can view a product in one month and purchase in the next. Detailed open/closed funnel analysis belongs in a separate module.

---

# 26. Refund metrics

```text
Refund value share = refund value / gross purchase revenue
Refund event rate = refund events / orders
```

The first metric measures financial impact; the second measures event frequency. One refund event can contain multiple items or a partial amount, so they do not measure the same thing.

---

# 27. MoM comparison

MoM joins a complete calendar month to the immediately preceding calendar month:

```text
Absolute change = current month − previous month
MoM % = (current month − previous month) / |previous month|
```

If the immediately preceding month is absent or incomplete, the comparison remains null. The calculation does not jump to the previous available row.

---

# 28. YoY comparison

YoY joins a complete calendar month to the same month one year earlier.

This is useful when the business has strong seasonality. At least 13 months of history are required for a current month to have a prior-year comparator.

If the comparison month is missing or incomplete, YoY remains null.

---

# 29. Percentage points versus percent change

Example:

```text
Previous purchase rate  2.0%
Current purchase rate   2.5%
```

The changes are:

```text
Absolute change  +0.5 percentage points
Relative change  +25%
```

The report stores and displays both. They should not be used interchangeably.

---

# 30. Complete-month rule

Partial months remain available in the monthly table, but cards, charts, and MoM/YoY comparisons prefer the latest complete month.

A month is marked complete when exported events cover every calendar day from the first through the last day of that month.

For example, a report run on September 12 can retain September rows while presenting August as the latest complete reporting month. This prevents a 12-day period from being compared with a full month.

---

# 31. Currency basis

The toolkit selects the reporting basis automatically:

```text
One purchase currency and local values available → local revenue
Multiple purchase currencies                   → USD revenue
```

Both local and USD columns remain in BigQuery.

Directly summing multiple local currencies would be invalid, so the toolkit switches to USD when a common basis is needed. Multi-currency results require reliable USD fields.

---

# 32. Basic cohort summary

`cohort_analysis()` groups identified customers by first purchase month.

For each cohort it reports:

- cohort size,
- orders,
- average observation days,
- gross, refund, and net revenue,
- mean and median observed LTV,
- orders per customer,
- repeat rate,
- AOV,
- refund share.

The table grain is one first-purchase month.

---

# 33. Cohort observation-age bias

Basic cohorts are not compared at equal customer age.

An older cohort has had more time to place repeat orders. Higher observed LTV can therefore reflect a longer observation period rather than better customer quality.

Month-0/month-1 retention, equal-age cumulative LTV, and cohort matrices are intentionally reserved for the separate cohort-analysis module.

Always review `average_observation_days` when comparing basic cohorts.

---

# 34. Chart interpretation

## Net revenue by LTV decile

Shows how total customer revenue is distributed from D1 to D10.

## Cumulative positive-revenue curve

Shows whether a small share of customers produces a large share of positive revenue.

## Monthly net purchase revenue

Reflects traffic, purchaser rate, AOV, purchase frequency, and refunds together.

## ARPU and ARPPU

Compare value across the active-user base and purchaser base.

## AOV and revenue per session

Compare order value with traffic value. If AOV rises while revenue per session falls, conversion may have weakened.

## Session purchase and repeat-purchaser rates

Show new conversion efficiency and monthly repeat behavior together.

## Basic cohort charts

Show cohort size and observed mean/median LTV. Observation-age differences must remain visible in interpretation.

---

# 35. HTML dashboard

```python
dashboard_path = analysis.generate_dashboard("ga4_ltv_dashboard.html")
```

The dashboard is a portable single HTML file with embedded chart images.

It includes:

- headline LTV cards,
- interpretation notes,
- LTV distribution and concentration,
- latest complete-month ecommerce cards,
- monthly trends,
- MoM/YoY table,
- basic cohort charts,
- decile table,
- data-quality checks.

The dashboard does not expose a row-level `user_id` list. Real client results should still be stored according to the organization's data-sharing policy.

---

# 36. When the analysis can mislead

Results require caution when:

- `user_id` coverage is low,
- transaction IDs are frequently missing,
- purchase revenue or currency is incorrect,
- refunds are missing or cannot be linked to customers,
- the observation history is too short for the natural repeat cycle,
- the selected period is dominated by a campaign or seasonal event,
- partial months are compared with full months,
- basic cohorts are treated as equal-age cohorts,
- revenue LTV is described as profit LTV.

---

# 37. Metrics that need another source

The four GA4 inputs cannot reliably produce:

```text
ROAS
CPA
CAC
CPC
CPM
profit LTV
LTV / CAC
contribution margin
product margin
```

These require media-cost, product-cost, commission, CRM, or finance data with compatible keys. The toolkit does not treat missing cost as zero.

---

# 38. Example management summary

```text
The analysis covers 42,600 purchasing customers identified by user_id in the selected GA4 history. Purchase-level user_id coverage is 79%, transaction ID coverage is 98%, and revenue coverage is 99%.

Observed mean LTV is TRY 2,180 and median LTV is TRY 760. The gap indicates that a relatively small high-value segment lifts the average. The highest-LTV 10% of customers contributes 41% of positive net revenue.

In the latest complete month, Ecommerce ARPU is TRY 126, ARPPU is TRY 1,580, and AOV is TRY 1,340. Net revenue increased 8% MoM while purchaser rate declined by 0.3 percentage points, suggesting that growth came primarily from order and purchaser value rather than conversion.

Basic first-purchase cohorts differ in observed LTV, but older cohorts have longer observation periods and should not be treated as equal-age performance comparisons.
```

---

# 39. Pre-analysis checklist

- [ ] Correct project, dataset, and table pattern
- [ ] Sufficient daily event history
- [ ] Reliable `user_id` implementation
- [ ] Transaction ID on purchase events
- [ ] Correct revenue and currency fields
- [ ] Refund events and values implemented
- [ ] Session parameters available
- [ ] Standard ecommerce events implemented
- [ ] Dry-run estimate reviewed

---

# 40. Post-analysis checklist

- [ ] Report `user_id` coverage with the result
- [ ] Interpret mean and median together
- [ ] Review P90/P95 and top deciles
- [ ] Investigate negative LTV before labeling customers
- [ ] Read refund share with gross and net revenue
- [ ] Confirm the reporting month is complete
- [ ] Confirm MoM and YoY comparison periods exist
- [ ] Express rate changes in percentage points where appropriate
- [ ] State that new purchasers are new within selected history
- [ ] Interpret basic cohorts with observation-age bias
- [ ] Describe the result as revenue LTV, not profit LTV

---

# 41. Summary

`ga4-ltv-toolkit` produces observed customer revenue LTV from GA4 BigQuery exports at `user_id` grain. It deduplicates purchases and refunds, exposes measurement coverage, reports distribution and concentration, and adds a monthly ecommerce-performance layer.

The monthly layer includes Ecommerce ARPU, ARPPU, AOV, net AOV, revenue per session, purchase frequency, conversion, repeat-purchase, and refund metrics. MoM and YoY comparisons use actual calendar periods and avoid promoting partial months.

The cohort section is intentionally basic. Equal-age retention and cumulative-LTV cohort analysis belong in a separate module.

The reliability of every conclusion depends on the quality of `user_id`, transaction ID, revenue, refund, session, and ecommerce-event implementation.
