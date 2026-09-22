CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_transaction_base`
PARTITION BY event_date
CLUSTER BY user_id, event_name AS
WITH raw AS (
  SELECT
    user_id,
    user_pseudo_id,
    event_name,
    SAFE.PARSE_DATE('%Y%m%d', event_date) AS event_date,
    TIMESTAMP_MICROS(event_timestamp) AS event_timestamp,
    event_timestamp AS event_timestamp_micros,
    event_bundle_sequence_id,
    event_server_timestamp_offset,
    NULLIF(TRIM(ecommerce.transaction_id), '') AS source_transaction_id,
    (
      SELECT COALESCE(
        ep.value.string_value,
        CAST(ep.value.int_value AS STRING),
        CAST(ep.value.double_value AS STRING)
      )
      FROM UNNEST(event_params) AS ep
      WHERE ep.key = 'currency'
      LIMIT 1
    ) AS currency,
    SAFE_CAST(ecommerce.purchase_revenue AS FLOAT64) AS purchase_revenue_local,
    SAFE_CAST(ecommerce.purchase_revenue_in_usd AS FLOAT64) AS purchase_revenue_usd,
    SAFE_CAST(ecommerce.refund_value AS FLOAT64) AS refund_value_local,
    SAFE_CAST(ecommerce.refund_value_in_usd AS FLOAT64) AS refund_value_usd
  FROM `{{SOURCE_TABLE}}`
  WHERE {{DAILY_TABLE_FILTER}}
    AND event_name IN ('purchase', 'refund')
),
keyed AS (
  SELECT
    *,
    CASE
      WHEN event_name = 'purchase' AND source_transaction_id IS NOT NULL THEN
        CONCAT(
          'purchase|',
          COALESCE(user_id, user_pseudo_id, '__unknown_user__'),
          '|', source_transaction_id
        )
      WHEN event_name = 'refund' AND source_transaction_id IS NOT NULL THEN
        CONCAT(
          'refund|',
          COALESCE(user_id, user_pseudo_id, '__unknown_user__'),
          '|', source_transaction_id,
          '|', CAST(event_timestamp_micros AS STRING),
          '|', CAST(COALESCE(refund_value_usd, refund_value_local, 0) AS STRING)
        )
      ELSE
        CONCAT(
          event_name, '|',
          COALESCE(user_id, user_pseudo_id, '__unknown_user__'),
          '|', CAST(event_timestamp_micros AS STRING),
          '|', CAST(COALESCE(event_bundle_sequence_id, -1) AS STRING)
        )
    END AS deduplication_key
  FROM raw
),
deduplicated AS (
  SELECT * EXCEPT(deduplication_rank)
  FROM (
    SELECT
      *,
      ROW_NUMBER() OVER (
        PARTITION BY deduplication_key
        ORDER BY
          COALESCE(event_server_timestamp_offset, 0) DESC,
          event_timestamp_micros DESC
      ) AS deduplication_rank
    FROM keyed
  )
  WHERE deduplication_rank = 1
)
SELECT
  user_id,
  user_pseudo_id,
  event_name,
  event_date,
  event_timestamp,
  source_transaction_id,
  deduplication_key AS transaction_event_key,
  currency,
  user_id IS NOT NULL AS analysis_eligible,
  source_transaction_id IS NULL AS transaction_id_missing,
  IF(event_name = 'purchase', 1, 0) AS purchase_event,
  IF(event_name = 'refund', 1, 0) AS refund_event,
  IF(event_name = 'purchase', COALESCE(purchase_revenue_local, 0), 0) AS gross_revenue_local,
  IF(event_name = 'refund', COALESCE(refund_value_local, 0), 0) AS refund_revenue_local,
  IF(event_name = 'purchase', COALESCE(purchase_revenue_local, 0), 0)
    - IF(event_name = 'refund', COALESCE(refund_value_local, 0), 0) AS net_revenue_local,
  IF(event_name = 'purchase', COALESCE(purchase_revenue_usd, 0), 0) AS gross_revenue_usd,
  IF(event_name = 'refund', COALESCE(refund_value_usd, 0), 0) AS refund_revenue_usd,
  IF(event_name = 'purchase', COALESCE(purchase_revenue_usd, 0), 0)
    - IF(event_name = 'refund', COALESCE(refund_value_usd, 0), 0) AS net_revenue_usd,
  IF(event_name = 'purchase', purchase_revenue_local IS NOT NULL, refund_value_local IS NOT NULL)
    AS local_value_present,
  IF(event_name = 'purchase', purchase_revenue_usd IS NOT NULL, refund_value_usd IS NOT NULL)
    AS usd_value_present,
  IF(
    event_name = 'purchase',
    purchase_revenue_local IS NOT NULL OR purchase_revenue_usd IS NOT NULL,
    refund_value_local IS NOT NULL OR refund_value_usd IS NOT NULL
  ) AS revenue_value_present
FROM deduplicated;
