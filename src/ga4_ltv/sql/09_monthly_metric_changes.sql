CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_monthly_metric_changes`
PARTITION BY month AS
WITH metric_choice AS (
  SELECT
    IF(
      distinct_purchase_currencies <= 1
        AND purchase_events_with_local_value > 0,
      'local',
      'usd'
    ) AS metric_basis,
    IF(
      distinct_purchase_currencies <= 1
        AND purchase_events_with_local_value > 0,
      COALESCE(purchase_currencies[SAFE_OFFSET(0)], 'LOCAL'),
      'USD'
    ) AS currency
  FROM `{{OUTPUT_DATASET}}.ltv_data_quality`
),
long_metrics AS (
  SELECT
    m.month,
    m.observed_start_date,
    m.observed_end_date,
    m.observed_event_days,
    m.is_complete_month,
    choice.metric_basis,
    choice.currency,
    metric.display_order,
    metric.metric_group,
    metric.metric_name,
    metric.metric_label,
    metric.metric_unit,
    metric.metric_value
  FROM `{{OUTPUT_DATASET}}.ltv_monthly_metrics` AS m
  CROSS JOIN metric_choice AS choice
  CROSS JOIN UNNEST([
    STRUCT(1 AS display_order, 'Kitle' AS metric_group, 'active_users' AS metric_name, 'Aktif kullanıcı' AS metric_label, 'count' AS metric_unit, CAST(m.active_users AS FLOAT64) AS metric_value),
    STRUCT(2, 'Kitle', 'new_users', 'Yeni kullanıcı', 'count', CAST(m.new_users AS FLOAT64)),
    STRUCT(3, 'Kitle', 'sessions', 'Oturum', 'count', CAST(m.sessions AS FLOAT64)),
    STRUCT(4, 'Kitle', 'engagement_rate', 'Etkileşim oranı', 'ratio', CAST(m.engagement_rate AS FLOAT64)),
    STRUCT(5, 'Kitle', 'sessions_per_active_user', 'Aktif kullanıcı başına oturum', 'number', CAST(m.sessions_per_active_user AS FLOAT64)),
    STRUCT(10, 'Ticaret', 'purchasers', 'Satın alan kullanıcı', 'count', CAST(m.purchasers AS FLOAT64)),
    STRUCT(11, 'Ticaret', 'orders', 'Sipariş', 'count', CAST(m.orders AS FLOAT64)),
    STRUCT(12, 'Ticaret', 'purchase_frequency', 'Satın alma sıklığı', 'number', CAST(m.purchase_frequency AS FLOAT64)),
    STRUCT(13, 'Ticaret', 'items_per_order', 'Sipariş başına ürün', 'number', CAST(m.items_per_order AS FLOAT64)),
    STRUCT(14, 'Ticaret', 'repeat_purchaser_rate', 'Aylık tekrar satın alan oranı', 'ratio', CAST(m.repeat_purchaser_rate AS FLOAT64)),
    STRUCT(15, 'Ticaret', 'new_purchaser_rate', 'Yeni satın alan oranı', 'ratio', CAST(m.new_purchaser_rate AS FLOAT64)),
    STRUCT(20, 'Gelir', 'gross_revenue', 'Brüt satın alma geliri', 'currency', CAST(IF(choice.metric_basis = 'local', m.gross_revenue_local, m.gross_revenue_usd) AS FLOAT64)),
    STRUCT(21, 'Gelir', 'net_revenue', 'Net satın alma geliri', 'currency', CAST(IF(choice.metric_basis = 'local', m.net_revenue_local, m.net_revenue_usd) AS FLOAT64)),
    STRUCT(22, 'Gelir', 'aov', 'Ortalama sipariş tutarı (AOV)', 'currency', CAST(IF(choice.metric_basis = 'local', m.average_order_value_local, m.average_order_value_usd) AS FLOAT64)),
    STRUCT(23, 'Gelir', 'net_aov', 'Net ortalama sipariş tutarı', 'currency', CAST(IF(choice.metric_basis = 'local', m.net_average_order_value_local, m.net_average_order_value_usd) AS FLOAT64)),
    STRUCT(24, 'Gelir', 'ecommerce_arpu', 'E-ticaret ARPU', 'currency', CAST(IF(choice.metric_basis = 'local', m.ecommerce_arpu_local, m.ecommerce_arpu_usd) AS FLOAT64)),
    STRUCT(25, 'Gelir', 'ecommerce_arppu', 'E-ticaret ARPPU', 'currency', CAST(IF(choice.metric_basis = 'local', m.ecommerce_arppu_local, m.ecommerce_arppu_usd) AS FLOAT64)),
    STRUCT(26, 'Gelir', 'revenue_per_session', 'Oturum başına gelir', 'currency', CAST(IF(choice.metric_basis = 'local', m.revenue_per_session_local, m.revenue_per_session_usd) AS FLOAT64)),
    STRUCT(30, 'Dönüşüm', 'purchaser_rate', 'Satın alan kullanıcı oranı', 'ratio', CAST(m.purchaser_rate AS FLOAT64)),
    STRUCT(31, 'Dönüşüm', 'purchase_session_rate', 'Oturum satın alma oranı', 'ratio', CAST(m.purchase_session_rate AS FLOAT64)),
    STRUCT(32, 'Dönüşüm', 'view_to_cart_user_rate', 'Ürün görüntülemeden sepete geçiş', 'ratio', CAST(m.view_to_cart_user_rate AS FLOAT64)),
    STRUCT(33, 'Dönüşüm', 'cart_to_checkout_user_rate', 'Sepetten ödeme başlangıcına geçiş', 'ratio', CAST(m.cart_to_checkout_user_rate AS FLOAT64)),
    STRUCT(34, 'Dönüşüm', 'checkout_to_purchase_user_rate', 'Ödeme başlangıcından satın almaya geçiş', 'ratio', CAST(m.checkout_to_purchase_user_rate AS FLOAT64)),
    STRUCT(35, 'Dönüşüm', 'purchase_to_view_user_rate', 'Ürün görüntülemeden satın almaya geçiş', 'ratio', CAST(m.purchase_to_view_user_rate AS FLOAT64)),
    STRUCT(40, 'Kalite', 'refund_value_share', 'İade tutarı payı', 'ratio', CAST(IF(choice.metric_basis = 'local', m.refund_value_share_local, m.refund_value_share_usd) AS FLOAT64)),
    STRUCT(41, 'Kalite', 'refund_event_rate', 'Sipariş başına iade olayı', 'ratio', CAST(m.refund_event_rate AS FLOAT64))
  ]) AS metric
),
changes AS (
  SELECT
    current.*,
    previous.metric_value AS previous_month_value,
    previous.is_complete_month AS previous_month_is_complete,
    previous_year.metric_value AS previous_year_value,
    previous_year.is_complete_month AS previous_year_is_complete
  FROM long_metrics AS current
  LEFT JOIN long_metrics AS previous
    ON current.metric_name = previous.metric_name
   AND previous.month = DATE_SUB(current.month, INTERVAL 1 MONTH)
  LEFT JOIN long_metrics AS previous_year
    ON current.metric_name = previous_year.metric_name
   AND previous_year.month = DATE_SUB(current.month, INTERVAL 1 YEAR)
)
SELECT
  *,
  IF(
    is_complete_month AND COALESCE(previous_month_is_complete, FALSE),
    metric_value - previous_month_value,
    NULL
  ) AS mom_absolute_change,
  IF(
    is_complete_month AND COALESCE(previous_month_is_complete, FALSE),
    SAFE_DIVIDE(metric_value - previous_month_value, ABS(previous_month_value)),
    NULL
  ) AS mom_change_pct,
  IF(
    is_complete_month AND COALESCE(previous_year_is_complete, FALSE),
    metric_value - previous_year_value,
    NULL
  ) AS yoy_absolute_change,
  IF(
    is_complete_month AND COALESCE(previous_year_is_complete, FALSE),
    SAFE_DIVIDE(metric_value - previous_year_value, ABS(previous_year_value)),
    NULL
  ) AS yoy_change_pct
FROM changes
ORDER BY month, display_order;
