CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_monthly_metrics`
PARTITION BY month AS
WITH raw AS (
  SELECT
    PARSE_DATE('%Y%m%d', event_date) AS event_day,
    DATE_TRUNC(PARSE_DATE('%Y%m%d', event_date), MONTH) AS month,
    user_id,
    user_pseudo_id,
    event_name,
    is_active_user,
    event_timestamp,
    event_bundle_sequence_id,
    event_server_timestamp_offset,
    NULLIF(TRIM(ecommerce.transaction_id), '') AS source_transaction_id,
    SAFE_CAST(ecommerce.purchase_revenue AS FLOAT64) AS purchase_revenue_local,
    SAFE_CAST(ecommerce.purchase_revenue_in_usd AS FLOAT64) AS purchase_revenue_usd,
    SAFE_CAST(ecommerce.refund_value AS FLOAT64) AS refund_value_local,
    SAFE_CAST(ecommerce.refund_value_in_usd AS FLOAT64) AS refund_value_usd,
    SAFE_CAST(ecommerce.total_item_quantity AS FLOAT64) AS total_item_quantity,
    (
      SELECT ep.value.int_value
      FROM UNNEST(event_params) AS ep
      WHERE ep.key = 'ga_session_id'
      LIMIT 1
    ) AS ga_session_id,
    COALESCE(
      (
        SELECT ep.value.int_value
        FROM UNNEST(event_params) AS ep
        WHERE ep.key = 'session_engaged'
        LIMIT 1
      ),
      SAFE_CAST(
        (
          SELECT ep.value.string_value
          FROM UNNEST(event_params) AS ep
          WHERE ep.key = 'session_engaged'
          LIMIT 1
        ) AS INT64
      ),
      0
    ) = 1 AS session_engaged
  FROM `{{SOURCE_TABLE}}`
  WHERE {{DAILY_TABLE_FILTER}}
),
events AS (
  SELECT
    *,
    IF(
      user_pseudo_id IS NULL OR ga_session_id IS NULL,
      NULL,
      CONCAT(user_pseudo_id, '-', CAST(ga_session_id AS STRING))
    ) AS session_key,
    CASE
      WHEN user_id IS NOT NULL THEN CONCAT('u:', user_id)
      WHEN user_pseudo_id IS NOT NULL THEN CONCAT('p:', user_pseudo_id)
      ELSE NULL
    END AS analytics_user_key
  FROM raw
),
event_metrics AS (
  SELECT
    month,
    MIN(event_day) AS observed_start_date,
    MAX(event_day) AS observed_end_date,
    COUNT(DISTINCT event_day) AS observed_event_days,
    COUNT(DISTINCT event_day) = EXTRACT(DAY FROM LAST_DAY(month))
      AND MIN(event_day) = month
      AND MAX(event_day) = LAST_DAY(month) AS is_complete_month,
    COUNT(*) AS events,
    COUNT(DISTINCT analytics_user_key) AS total_users,
    COUNT(
      DISTINCT IF(
        COALESCE(is_active_user, FALSE) OR event_name = 'user_engagement',
        analytics_user_key,
        NULL
      )
    ) AS active_users,
    COUNT(DISTINCT user_id) AS identified_users,
    COUNT(DISTINCT IF(event_name IN ('first_visit', 'first_open'), analytics_user_key, NULL)) AS new_users,
    COUNT(DISTINCT session_key) AS sessions,
    COUNT(DISTINCT IF(session_engaged, session_key, NULL)) AS engaged_sessions,
    COUNT(DISTINCT IF(event_name = 'view_item', analytics_user_key, NULL)) AS view_item_users,
    COUNT(DISTINCT IF(event_name = 'add_to_cart', analytics_user_key, NULL)) AS add_to_cart_users,
    COUNT(DISTINCT IF(event_name = 'begin_checkout', analytics_user_key, NULL)) AS begin_checkout_users,
    COUNT(DISTINCT IF(event_name = 'purchase', analytics_user_key, NULL)) AS purchase_users,
    COUNT(DISTINCT IF(event_name = 'view_item', session_key, NULL)) AS view_item_sessions,
    COUNT(DISTINCT IF(event_name = 'add_to_cart', session_key, NULL)) AS add_to_cart_sessions,
    COUNT(DISTINCT IF(event_name = 'begin_checkout', session_key, NULL)) AS begin_checkout_sessions,
    COUNT(DISTINCT IF(event_name = 'purchase', session_key, NULL)) AS purchase_sessions
  FROM events
  GROUP BY month
),
commerce_keyed AS (
  SELECT
    *,
    CASE
      WHEN event_name = 'purchase' AND source_transaction_id IS NOT NULL THEN
        CONCAT('purchase|', COALESCE(analytics_user_key, '__unknown__'), '|', source_transaction_id)
      WHEN event_name = 'refund' AND source_transaction_id IS NOT NULL THEN
        CONCAT(
          'refund|', COALESCE(analytics_user_key, '__unknown__'), '|', source_transaction_id,
          '|', CAST(event_timestamp AS STRING),
          '|', CAST(COALESCE(refund_value_usd, refund_value_local, 0) AS STRING)
        )
      ELSE
        CONCAT(
          event_name, '|', COALESCE(analytics_user_key, '__unknown__'),
          '|', CAST(event_timestamp AS STRING),
          '|', CAST(COALESCE(event_bundle_sequence_id, -1) AS STRING)
        )
    END AS deduplication_key
  FROM events
  WHERE event_name IN ('purchase', 'refund')
),
commerce AS (
  SELECT * EXCEPT(deduplication_rank)
  FROM (
    SELECT
      *,
      ROW_NUMBER() OVER (
        PARTITION BY deduplication_key
        ORDER BY COALESCE(event_server_timestamp_offset, 0) DESC, event_timestamp DESC
      ) AS deduplication_rank
    FROM commerce_keyed
  )
  WHERE deduplication_rank = 1
),
purchaser_month AS (
  SELECT
    month,
    analytics_user_key,
    COUNTIF(event_name = 'purchase') AS orders
  FROM commerce
  WHERE analytics_user_key IS NOT NULL
  GROUP BY month, analytics_user_key
  HAVING COUNTIF(event_name = 'purchase') > 0
),
repeat_metrics AS (
  SELECT
    month,
    COUNT(*) AS purchasers,
    COUNTIF(orders >= 2) AS repeat_purchasers
  FROM purchaser_month
  GROUP BY month
),
first_purchase AS (
  SELECT
    analytics_user_key,
    MIN(month) AS first_purchase_month
  FROM commerce
  WHERE event_name = 'purchase'
    AND analytics_user_key IS NOT NULL
  GROUP BY analytics_user_key
),
new_purchaser_metrics AS (
  SELECT
    first_purchase_month AS month,
    COUNT(*) AS new_purchasers
  FROM first_purchase
  GROUP BY first_purchase_month
),
commerce_metrics AS (
  SELECT
    month,
    COUNTIF(event_name = 'purchase') AS orders,
    COUNTIF(event_name = 'refund') AS refund_events,
    COUNT(DISTINCT IF(event_name = 'purchase', analytics_user_key, NULL)) AS purchasers,
    COUNT(DISTINCT IF(event_name = 'purchase', user_id, NULL)) AS identified_purchasers,
    SUM(IF(event_name = 'purchase', COALESCE(total_item_quantity, 0), 0)) AS items_purchased,
    SUM(IF(event_name = 'purchase', COALESCE(purchase_revenue_local, 0), 0)) AS gross_revenue_local,
    SUM(IF(event_name = 'refund', COALESCE(refund_value_local, 0), 0)) AS refund_revenue_local,
    SUM(IF(event_name = 'purchase', COALESCE(purchase_revenue_local, 0), 0))
      - SUM(IF(event_name = 'refund', COALESCE(refund_value_local, 0), 0)) AS net_revenue_local,
    SUM(IF(event_name = 'purchase', COALESCE(purchase_revenue_usd, 0), 0)) AS gross_revenue_usd,
    SUM(IF(event_name = 'refund', COALESCE(refund_value_usd, 0), 0)) AS refund_revenue_usd,
    SUM(IF(event_name = 'purchase', COALESCE(purchase_revenue_usd, 0), 0))
      - SUM(IF(event_name = 'refund', COALESCE(refund_value_usd, 0), 0)) AS net_revenue_usd
  FROM commerce
  GROUP BY month
),
combined AS (
  SELECT
    e.*,
    COALESCE(c.orders, 0) AS orders,
    COALESCE(c.refund_events, 0) AS refund_events,
    COALESCE(c.purchasers, 0) AS purchasers,
    COALESCE(c.identified_purchasers, 0) AS identified_purchasers,
    COALESCE(r.repeat_purchasers, 0) AS repeat_purchasers,
    COALESCE(n.new_purchasers, 0) AS new_purchasers,
    COALESCE(c.items_purchased, 0) AS items_purchased,
    COALESCE(c.gross_revenue_local, 0) AS gross_revenue_local,
    COALESCE(c.refund_revenue_local, 0) AS refund_revenue_local,
    COALESCE(c.net_revenue_local, 0) AS net_revenue_local,
    COALESCE(c.gross_revenue_usd, 0) AS gross_revenue_usd,
    COALESCE(c.refund_revenue_usd, 0) AS refund_revenue_usd,
    COALESCE(c.net_revenue_usd, 0) AS net_revenue_usd
  FROM event_metrics AS e
  LEFT JOIN commerce_metrics AS c USING (month)
  LEFT JOIN repeat_metrics AS r USING (month)
  LEFT JOIN new_purchaser_metrics AS n USING (month)
)
SELECT
  *,
  SAFE_DIVIDE(engaged_sessions, sessions) AS engagement_rate,
  1 - SAFE_DIVIDE(engaged_sessions, sessions) AS bounce_rate,
  SAFE_DIVIDE(new_users, active_users) AS new_user_rate,
  SAFE_DIVIDE(sessions, active_users) AS sessions_per_active_user,
  SAFE_DIVIDE(events, active_users) AS events_per_active_user,
  SAFE_DIVIDE(purchasers, active_users) AS purchaser_rate,
  SAFE_DIVIDE(identified_purchasers, identified_users) AS identified_purchaser_rate,
  SAFE_DIVIDE(purchase_sessions, sessions) AS purchase_session_rate,
  SAFE_DIVIDE(view_item_sessions, sessions) AS view_item_session_rate,
  SAFE_DIVIDE(add_to_cart_sessions, sessions) AS add_to_cart_session_rate,
  SAFE_DIVIDE(begin_checkout_sessions, sessions) AS begin_checkout_session_rate,
  SAFE_DIVIDE(add_to_cart_users, view_item_users) AS view_to_cart_user_rate,
  SAFE_DIVIDE(begin_checkout_users, add_to_cart_users) AS cart_to_checkout_user_rate,
  SAFE_DIVIDE(purchase_users, begin_checkout_users) AS checkout_to_purchase_user_rate,
  SAFE_DIVIDE(purchase_users, view_item_users) AS purchase_to_view_user_rate,
  SAFE_DIVIDE(orders, purchasers) AS purchase_frequency,
  SAFE_DIVIDE(repeat_purchasers, purchasers) AS repeat_purchaser_rate,
  SAFE_DIVIDE(new_purchasers, purchasers) AS new_purchaser_rate,
  SAFE_DIVIDE(items_purchased, orders) AS items_per_order,
  SAFE_DIVIDE(gross_revenue_local, orders) AS average_order_value_local,
  SAFE_DIVIDE(net_revenue_local, orders) AS net_average_order_value_local,
  SAFE_DIVIDE(net_revenue_local, active_users) AS ecommerce_arpu_local,
  SAFE_DIVIDE(net_revenue_local, purchasers) AS ecommerce_arppu_local,
  SAFE_DIVIDE(net_revenue_local, sessions) AS revenue_per_session_local,
  SAFE_DIVIDE(refund_revenue_local, gross_revenue_local) AS refund_value_share_local,
  SAFE_DIVIDE(gross_revenue_usd, orders) AS average_order_value_usd,
  SAFE_DIVIDE(net_revenue_usd, orders) AS net_average_order_value_usd,
  SAFE_DIVIDE(net_revenue_usd, active_users) AS ecommerce_arpu_usd,
  SAFE_DIVIDE(net_revenue_usd, purchasers) AS ecommerce_arppu_usd,
  SAFE_DIVIDE(net_revenue_usd, sessions) AS revenue_per_session_usd,
  SAFE_DIVIDE(refund_revenue_usd, gross_revenue_usd) AS refund_value_share_usd,
  SAFE_DIVIDE(refund_events, orders) AS refund_event_rate
FROM combined
ORDER BY month;
