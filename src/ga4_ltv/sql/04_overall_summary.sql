CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_overall_summary` AS
WITH stats AS (
  SELECT
    COUNT(*) AS customers,
    SUM(order_count) AS orders,
    COUNTIF(repeat_customer) AS repeat_customers,
    COUNTIF(net_revenue_local < 0 OR net_revenue_usd < 0) AS negative_ltv_customers,
    MIN(first_purchase_date) AS first_purchase_date,
    MAX(analysis_end_date) AS analysis_end_date,
    SUM(gross_revenue_local) AS gross_revenue_local,
    SUM(refund_revenue_local) AS refund_revenue_local,
    SUM(net_revenue_local) AS net_revenue_local,
    AVG(net_revenue_local) AS average_ltv_local,
    APPROX_QUANTILES(net_revenue_local, 100) AS ltv_quantiles_local,
    SUM(gross_revenue_usd) AS gross_revenue_usd,
    SUM(refund_revenue_usd) AS refund_revenue_usd,
    SUM(net_revenue_usd) AS net_revenue_usd,
    AVG(net_revenue_usd) AS average_ltv_usd,
    APPROX_QUANTILES(net_revenue_usd, 100) AS ltv_quantiles_usd
  FROM `{{OUTPUT_DATASET}}.ltv_customer_summary`
)
SELECT
  customers,
  orders,
  repeat_customers,
  negative_ltv_customers,
  first_purchase_date,
  analysis_end_date,
  gross_revenue_local,
  refund_revenue_local,
  net_revenue_local,
  average_ltv_local,
  ltv_quantiles_local[SAFE_OFFSET(50)] AS median_ltv_local,
  ltv_quantiles_local[SAFE_OFFSET(75)] AS p75_ltv_local,
  ltv_quantiles_local[SAFE_OFFSET(90)] AS p90_ltv_local,
  ltv_quantiles_local[SAFE_OFFSET(95)] AS p95_ltv_local,
  gross_revenue_usd,
  refund_revenue_usd,
  net_revenue_usd,
  average_ltv_usd,
  ltv_quantiles_usd[SAFE_OFFSET(50)] AS median_ltv_usd,
  ltv_quantiles_usd[SAFE_OFFSET(75)] AS p75_ltv_usd,
  ltv_quantiles_usd[SAFE_OFFSET(90)] AS p90_ltv_usd,
  ltv_quantiles_usd[SAFE_OFFSET(95)] AS p95_ltv_usd,
  SAFE_DIVIDE(repeat_customers, customers) AS repeat_customer_rate,
  SAFE_DIVIDE(orders, customers) AS orders_per_customer,
  SAFE_DIVIDE(gross_revenue_local, orders) AS average_order_value_local,
  SAFE_DIVIDE(gross_revenue_usd, orders) AS average_order_value_usd,
  SAFE_DIVIDE(refund_revenue_local, gross_revenue_local) AS refund_share_local,
  SAFE_DIVIDE(refund_revenue_usd, gross_revenue_usd) AS refund_share_usd
FROM stats;

