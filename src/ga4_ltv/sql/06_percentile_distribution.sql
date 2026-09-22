CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_percentile_distribution` AS
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
    NTILE(100) OVER (
      ORDER BY
        IF(m.metric_basis = 'local', c.net_revenue_local, c.net_revenue_usd) DESC,
        c.user_id
    ) AS ltv_percentile
  FROM `{{OUTPUT_DATASET}}.ltv_customer_summary` AS c
  CROSS JOIN metric_choice AS m
),
aggregated AS (
  SELECT
    ltv_percentile,
    COUNT(*) AS customers,
    SUM(GREATEST(net_revenue_local, 0)) AS positive_net_revenue_local,
    SUM(GREATEST(net_revenue_usd, 0)) AS positive_net_revenue_usd,
    AVG(net_revenue_local) AS average_ltv_local,
    AVG(net_revenue_usd) AS average_ltv_usd
  FROM ranked
  GROUP BY ltv_percentile
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
  SAFE_DIVIDE(
    SUM(a.customers) OVER (ORDER BY a.ltv_percentile),
    t.customers
  ) AS cumulative_customer_share,
  SAFE_DIVIDE(
    SUM(a.positive_net_revenue_local) OVER (ORDER BY a.ltv_percentile),
    t.positive_net_revenue_local
  ) AS cumulative_positive_revenue_share_local,
  SAFE_DIVIDE(
    SUM(a.positive_net_revenue_usd) OVER (ORDER BY a.ltv_percentile),
    t.positive_net_revenue_usd
  ) AS cumulative_positive_revenue_share_usd
FROM aggregated AS a
CROSS JOIN totals AS t
ORDER BY a.ltv_percentile;
