CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_decile_summary` AS
WITH metric_choice AS (
  SELECT
    IF(
      distinct_purchase_currencies <= 1
        AND purchase_events_with_local_value > 0,
      'local',
      'usd'
    ) AS metric_basis
  FROM `{{OUTPUT_DATASET}}.ltv_data_quality`
),
ranked AS (
  SELECT
    c.*,
    NTILE(10) OVER (
      ORDER BY
        IF(m.metric_basis = 'local', c.net_revenue_local, c.net_revenue_usd) DESC,
        c.user_id
    ) AS ltv_decile
  FROM `{{OUTPUT_DATASET}}.ltv_customer_summary` AS c
  CROSS JOIN metric_choice AS m
),
aggregated AS (
  SELECT
    ltv_decile,
    COUNT(*) AS customers,
    SUM(order_count) AS orders,
    SUM(net_revenue_local) AS net_revenue_local,
    AVG(net_revenue_local) AS average_ltv_local,
    MIN(net_revenue_local) AS minimum_ltv_local,
    MAX(net_revenue_local) AS maximum_ltv_local,
    SUM(net_revenue_usd) AS net_revenue_usd,
    AVG(net_revenue_usd) AS average_ltv_usd,
    MIN(net_revenue_usd) AS minimum_ltv_usd,
    MAX(net_revenue_usd) AS maximum_ltv_usd,
    SUM(GREATEST(net_revenue_local, 0)) AS positive_net_revenue_local,
    SUM(GREATEST(net_revenue_usd, 0)) AS positive_net_revenue_usd,
    SAFE_DIVIDE(COUNTIF(repeat_customer), COUNT(*)) AS repeat_customer_rate
  FROM ranked
  GROUP BY ltv_decile
),
totals AS (
  SELECT
    SUM(customers) AS customers,
    SUM(positive_net_revenue_local) AS positive_net_revenue_local,
    SUM(positive_net_revenue_usd) AS positive_net_revenue_usd
  FROM aggregated
)
SELECT
  a.*,
  SAFE_DIVIDE(a.customers, t.customers) AS customer_share,
  SAFE_DIVIDE(a.positive_net_revenue_local, t.positive_net_revenue_local) AS positive_revenue_share_local,
  SAFE_DIVIDE(a.positive_net_revenue_usd, t.positive_net_revenue_usd) AS positive_revenue_share_usd,
  SAFE_DIVIDE(
    SUM(a.customers) OVER (ORDER BY a.ltv_decile),
    t.customers
  ) AS cumulative_customer_share,
  SAFE_DIVIDE(
    SUM(a.positive_net_revenue_local) OVER (ORDER BY a.ltv_decile),
    t.positive_net_revenue_local
  ) AS cumulative_positive_revenue_share_local,
  SAFE_DIVIDE(
    SUM(a.positive_net_revenue_usd) OVER (ORDER BY a.ltv_decile),
    t.positive_net_revenue_usd
  ) AS cumulative_positive_revenue_share_usd
FROM aggregated AS a
CROSS JOIN totals AS t
ORDER BY a.ltv_decile;
