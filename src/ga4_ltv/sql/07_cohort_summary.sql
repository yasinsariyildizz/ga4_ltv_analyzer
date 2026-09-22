CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_cohort_summary`
PARTITION BY cohort_month AS
WITH cohort_rollup AS (
  SELECT
    first_purchase_month AS cohort_month,
    COUNT(*) AS cohort_size,
    SUM(order_count) AS orders,
    COUNTIF(repeat_customer) AS repeat_customers,
    AVG(observed_days_since_first_purchase) AS average_observation_days,
    SUM(gross_revenue_local) AS gross_revenue_local,
    SUM(refund_revenue_local) AS refund_revenue_local,
    SUM(net_revenue_local) AS net_revenue_local,
    AVG(net_revenue_local) AS average_ltv_local,
    APPROX_QUANTILES(net_revenue_local, 100)[SAFE_OFFSET(50)] AS median_ltv_local,
    SUM(gross_revenue_usd) AS gross_revenue_usd,
    SUM(refund_revenue_usd) AS refund_revenue_usd,
    SUM(net_revenue_usd) AS net_revenue_usd,
    AVG(net_revenue_usd) AS average_ltv_usd,
    APPROX_QUANTILES(net_revenue_usd, 100)[SAFE_OFFSET(50)] AS median_ltv_usd
  FROM `{{OUTPUT_DATASET}}.ltv_customer_summary`
  GROUP BY first_purchase_month
)
SELECT
  *,
  SAFE_DIVIDE(orders, cohort_size) AS orders_per_customer,
  SAFE_DIVIDE(repeat_customers, cohort_size) AS repeat_customer_rate,
  SAFE_DIVIDE(gross_revenue_local, orders) AS average_order_value_local,
  SAFE_DIVIDE(gross_revenue_usd, orders) AS average_order_value_usd,
  SAFE_DIVIDE(refund_revenue_local, gross_revenue_local) AS refund_share_local,
  SAFE_DIVIDE(refund_revenue_usd, gross_revenue_usd) AS refund_share_usd
FROM cohort_rollup
ORDER BY cohort_month;
