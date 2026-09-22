CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_data_quality` AS
SELECT
  MIN(event_date) AS data_start_date,
  MAX(event_date) AS data_end_date,
  COUNT(*) AS commerce_events,
  COUNTIF(event_name = 'purchase') AS purchase_events,
  COUNTIF(event_name = 'refund') AS refund_events,
  COUNTIF(event_name = 'purchase' AND analysis_eligible) AS eligible_purchase_events,
  COUNTIF(event_name = 'purchase' AND NOT analysis_eligible) AS purchase_events_missing_user_id,
  COUNTIF(event_name = 'purchase' AND transaction_id_missing) AS purchase_events_missing_transaction_id,
  COUNTIF(event_name = 'purchase' AND NOT revenue_value_present) AS purchase_events_missing_revenue,
  COUNTIF(event_name = 'purchase' AND local_value_present) AS purchase_events_with_local_value,
  COUNTIF(event_name = 'purchase' AND usd_value_present) AS purchase_events_with_usd_value,
  COUNT(DISTINCT IF(event_name = 'purchase', currency, NULL)) AS distinct_purchase_currencies,
  ARRAY_AGG(
    DISTINCT IF(event_name = 'purchase', currency, NULL)
    IGNORE NULLS ORDER BY IF(event_name = 'purchase', currency, NULL) LIMIT 10
  ) AS purchase_currencies,
  SAFE_DIVIDE(
    COUNTIF(event_name = 'purchase' AND analysis_eligible),
    COUNTIF(event_name = 'purchase')
  ) AS user_id_coverage_rate,
  SAFE_DIVIDE(
    COUNTIF(event_name = 'purchase' AND NOT transaction_id_missing),
    COUNTIF(event_name = 'purchase')
  ) AS transaction_id_coverage_rate,
  SAFE_DIVIDE(
    COUNTIF(event_name = 'purchase' AND revenue_value_present),
    COUNTIF(event_name = 'purchase')
  ) AS revenue_coverage_rate
FROM `{{OUTPUT_DATASET}}.ltv_transaction_base`;
