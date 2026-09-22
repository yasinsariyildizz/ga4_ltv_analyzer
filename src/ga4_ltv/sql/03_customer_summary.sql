CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_customer_summary`
CLUSTER BY repeat_customer AS
WITH data_bounds AS (
  SELECT MAX(event_date) AS data_end_date
  FROM `{{OUTPUT_DATASET}}.ltv_transaction_base`
),
customer_rollup AS (
  SELECT
    user_id,
    MIN(IF(event_name = 'purchase', event_date, NULL)) AS first_purchase_date,
    MAX(IF(event_name = 'purchase', event_date, NULL)) AS last_purchase_date,
    COUNTIF(event_name = 'purchase') AS order_count,
    COUNTIF(event_name = 'refund') AS refund_event_count,
    SUM(gross_revenue_local) AS gross_revenue_local,
    SUM(refund_revenue_local) AS refund_revenue_local,
    SUM(net_revenue_local) AS net_revenue_local,
    SUM(gross_revenue_usd) AS gross_revenue_usd,
    SUM(refund_revenue_usd) AS refund_revenue_usd,
    SUM(net_revenue_usd) AS net_revenue_usd
  FROM `{{OUTPUT_DATASET}}.ltv_transaction_base`
  WHERE analysis_eligible
  GROUP BY user_id
  HAVING COUNTIF(event_name = 'purchase') > 0
)
SELECT
  c.user_id,
  c.first_purchase_date,
  c.last_purchase_date,
  DATE_TRUNC(c.first_purchase_date, MONTH) AS first_purchase_month,
  c.order_count,
  c.refund_event_count,
  c.order_count >= 2 AS repeat_customer,
  DATE_DIFF(c.last_purchase_date, c.first_purchase_date, DAY) AS purchase_span_days,
  DATE_DIFF(b.data_end_date, c.first_purchase_date, DAY) AS observed_days_since_first_purchase,
  DATE_DIFF(b.data_end_date, c.last_purchase_date, DAY) AS days_since_last_purchase,
  c.gross_revenue_local,
  c.refund_revenue_local,
  c.net_revenue_local,
  SAFE_DIVIDE(c.gross_revenue_local, c.order_count) AS average_order_value_local,
  c.gross_revenue_usd,
  c.refund_revenue_usd,
  c.net_revenue_usd,
  SAFE_DIVIDE(c.gross_revenue_usd, c.order_count) AS average_order_value_usd,
  b.data_end_date AS analysis_end_date
FROM customer_rollup AS c
CROSS JOIN data_bounds AS b;

