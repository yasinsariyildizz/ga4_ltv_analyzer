"""All-in-one GA4 observed LTV module for direct Colab upload.

Generated from ga4-ltv-toolkit 0.2.0.
"""

from __future__ import annotations

__all__ = ["LTVAnalyzer"]
__version__ = "0.2.0"

import base64
from datetime import datetime, timezone
import html
from io import BytesIO
from pathlib import Path
import re
from typing import Any

from google.api_core.exceptions import NotFound
from google.cloud import bigquery


_PROJECT_ID = re.compile(r"^[a-z][a-z0-9\-:.]{4,62}[a-z0-9]$")
_DATASET_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")
_TABLE_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\*)?$")

_SQL_TEMPLATES = {'01_transaction_base.sql': 'CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_transaction_base`\n'
                            'PARTITION BY event_date\n'
                            'CLUSTER BY user_id, event_name AS\n'
                            'WITH raw AS (\n'
                            '  SELECT\n'
                            '    user_id,\n'
                            '    user_pseudo_id,\n'
                            '    event_name,\n'
                            "    SAFE.PARSE_DATE('%Y%m%d', event_date) AS event_date,\n"
                            '    TIMESTAMP_MICROS(event_timestamp) AS event_timestamp,\n'
                            '    event_timestamp AS event_timestamp_micros,\n'
                            '    event_bundle_sequence_id,\n'
                            '    event_server_timestamp_offset,\n'
                            "    NULLIF(TRIM(ecommerce.transaction_id), '') AS "
                            'source_transaction_id,\n'
                            '    (\n'
                            '      SELECT COALESCE(\n'
                            '        ep.value.string_value,\n'
                            '        CAST(ep.value.int_value AS STRING),\n'
                            '        CAST(ep.value.double_value AS STRING)\n'
                            '      )\n'
                            '      FROM UNNEST(event_params) AS ep\n'
                            "      WHERE ep.key = 'currency'\n"
                            '      LIMIT 1\n'
                            '    ) AS currency,\n'
                            '    SAFE_CAST(ecommerce.purchase_revenue AS FLOAT64) AS '
                            'purchase_revenue_local,\n'
                            '    SAFE_CAST(ecommerce.purchase_revenue_in_usd AS FLOAT64) AS '
                            'purchase_revenue_usd,\n'
                            '    SAFE_CAST(ecommerce.refund_value AS FLOAT64) AS '
                            'refund_value_local,\n'
                            '    SAFE_CAST(ecommerce.refund_value_in_usd AS FLOAT64) AS '
                            'refund_value_usd\n'
                            '  FROM `{{SOURCE_TABLE}}`\n'
                            '  WHERE {{DAILY_TABLE_FILTER}}\n'
                            "    AND event_name IN ('purchase', 'refund')\n"
                            '),\n'
                            'keyed AS (\n'
                            '  SELECT\n'
                            '    *,\n'
                            '    CASE\n'
                            "      WHEN event_name = 'purchase' AND source_transaction_id IS NOT "
                            'NULL THEN\n'
                            '        CONCAT(\n'
                            "          'purchase|',\n"
                            "          COALESCE(user_id, user_pseudo_id, '__unknown_user__'),\n"
                            "          '|', source_transaction_id\n"
                            '        )\n'
                            "      WHEN event_name = 'refund' AND source_transaction_id IS NOT "
                            'NULL THEN\n'
                            '        CONCAT(\n'
                            "          'refund|',\n"
                            "          COALESCE(user_id, user_pseudo_id, '__unknown_user__'),\n"
                            "          '|', source_transaction_id,\n"
                            "          '|', CAST(event_timestamp_micros AS STRING),\n"
                            "          '|', CAST(COALESCE(refund_value_usd, refund_value_local, 0) "
                            'AS STRING)\n'
                            '        )\n'
                            '      ELSE\n'
                            '        CONCAT(\n'
                            "          event_name, '|',\n"
                            "          COALESCE(user_id, user_pseudo_id, '__unknown_user__'),\n"
                            "          '|', CAST(event_timestamp_micros AS STRING),\n"
                            "          '|', CAST(COALESCE(event_bundle_sequence_id, -1) AS "
                            'STRING)\n'
                            '        )\n'
                            '    END AS deduplication_key\n'
                            '  FROM raw\n'
                            '),\n'
                            'deduplicated AS (\n'
                            '  SELECT * EXCEPT(deduplication_rank)\n'
                            '  FROM (\n'
                            '    SELECT\n'
                            '      *,\n'
                            '      ROW_NUMBER() OVER (\n'
                            '        PARTITION BY deduplication_key\n'
                            '        ORDER BY\n'
                            '          COALESCE(event_server_timestamp_offset, 0) DESC,\n'
                            '          event_timestamp_micros DESC\n'
                            '      ) AS deduplication_rank\n'
                            '    FROM keyed\n'
                            '  )\n'
                            '  WHERE deduplication_rank = 1\n'
                            ')\n'
                            'SELECT\n'
                            '  user_id,\n'
                            '  user_pseudo_id,\n'
                            '  event_name,\n'
                            '  event_date,\n'
                            '  event_timestamp,\n'
                            '  source_transaction_id,\n'
                            '  deduplication_key AS transaction_event_key,\n'
                            '  currency,\n'
                            '  user_id IS NOT NULL AS analysis_eligible,\n'
                            '  source_transaction_id IS NULL AS transaction_id_missing,\n'
                            "  IF(event_name = 'purchase', 1, 0) AS purchase_event,\n"
                            "  IF(event_name = 'refund', 1, 0) AS refund_event,\n"
                            "  IF(event_name = 'purchase', COALESCE(purchase_revenue_local, 0), 0) "
                            'AS gross_revenue_local,\n'
                            "  IF(event_name = 'refund', COALESCE(refund_value_local, 0), 0) AS "
                            'refund_revenue_local,\n'
                            "  IF(event_name = 'purchase', COALESCE(purchase_revenue_local, 0), "
                            '0)\n'
                            "    - IF(event_name = 'refund', COALESCE(refund_value_local, 0), 0) "
                            'AS net_revenue_local,\n'
                            "  IF(event_name = 'purchase', COALESCE(purchase_revenue_usd, 0), 0) "
                            'AS gross_revenue_usd,\n'
                            "  IF(event_name = 'refund', COALESCE(refund_value_usd, 0), 0) AS "
                            'refund_revenue_usd,\n'
                            "  IF(event_name = 'purchase', COALESCE(purchase_revenue_usd, 0), 0)\n"
                            "    - IF(event_name = 'refund', COALESCE(refund_value_usd, 0), 0) AS "
                            'net_revenue_usd,\n'
                            "  IF(event_name = 'purchase', purchase_revenue_local IS NOT NULL, "
                            'refund_value_local IS NOT NULL)\n'
                            '    AS local_value_present,\n'
                            "  IF(event_name = 'purchase', purchase_revenue_usd IS NOT NULL, "
                            'refund_value_usd IS NOT NULL)\n'
                            '    AS usd_value_present,\n'
                            '  IF(\n'
                            "    event_name = 'purchase',\n"
                            '    purchase_revenue_local IS NOT NULL OR purchase_revenue_usd IS NOT '
                            'NULL,\n'
                            '    refund_value_local IS NOT NULL OR refund_value_usd IS NOT NULL\n'
                            '  ) AS revenue_value_present\n'
                            'FROM deduplicated;\n',
 '02_data_quality.sql': 'CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_data_quality` AS\n'
                        'SELECT\n'
                        '  MIN(event_date) AS data_start_date,\n'
                        '  MAX(event_date) AS data_end_date,\n'
                        '  COUNT(*) AS commerce_events,\n'
                        "  COUNTIF(event_name = 'purchase') AS purchase_events,\n"
                        "  COUNTIF(event_name = 'refund') AS refund_events,\n"
                        "  COUNTIF(event_name = 'purchase' AND analysis_eligible) AS "
                        'eligible_purchase_events,\n'
                        "  COUNTIF(event_name = 'purchase' AND NOT analysis_eligible) AS "
                        'purchase_events_missing_user_id,\n'
                        "  COUNTIF(event_name = 'purchase' AND transaction_id_missing) AS "
                        'purchase_events_missing_transaction_id,\n'
                        "  COUNTIF(event_name = 'purchase' AND NOT revenue_value_present) AS "
                        'purchase_events_missing_revenue,\n'
                        "  COUNTIF(event_name = 'purchase' AND local_value_present) AS "
                        'purchase_events_with_local_value,\n'
                        "  COUNTIF(event_name = 'purchase' AND usd_value_present) AS "
                        'purchase_events_with_usd_value,\n'
                        "  COUNT(DISTINCT IF(event_name = 'purchase', currency, NULL)) AS "
                        'distinct_purchase_currencies,\n'
                        '  ARRAY_AGG(\n'
                        "    DISTINCT IF(event_name = 'purchase', currency, NULL)\n"
                        "    IGNORE NULLS ORDER BY IF(event_name = 'purchase', currency, NULL) "
                        'LIMIT 10\n'
                        '  ) AS purchase_currencies,\n'
                        '  SAFE_DIVIDE(\n'
                        "    COUNTIF(event_name = 'purchase' AND analysis_eligible),\n"
                        "    COUNTIF(event_name = 'purchase')\n"
                        '  ) AS user_id_coverage_rate,\n'
                        '  SAFE_DIVIDE(\n'
                        "    COUNTIF(event_name = 'purchase' AND NOT transaction_id_missing),\n"
                        "    COUNTIF(event_name = 'purchase')\n"
                        '  ) AS transaction_id_coverage_rate,\n'
                        '  SAFE_DIVIDE(\n'
                        "    COUNTIF(event_name = 'purchase' AND revenue_value_present),\n"
                        "    COUNTIF(event_name = 'purchase')\n"
                        '  ) AS revenue_coverage_rate\n'
                        'FROM `{{OUTPUT_DATASET}}.ltv_transaction_base`;\n',
 '03_customer_summary.sql': 'CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_customer_summary`\n'
                            'CLUSTER BY repeat_customer AS\n'
                            'WITH data_bounds AS (\n'
                            '  SELECT MAX(event_date) AS data_end_date\n'
                            '  FROM `{{OUTPUT_DATASET}}.ltv_transaction_base`\n'
                            '),\n'
                            'customer_rollup AS (\n'
                            '  SELECT\n'
                            '    user_id,\n'
                            "    MIN(IF(event_name = 'purchase', event_date, NULL)) AS "
                            'first_purchase_date,\n'
                            "    MAX(IF(event_name = 'purchase', event_date, NULL)) AS "
                            'last_purchase_date,\n'
                            "    COUNTIF(event_name = 'purchase') AS order_count,\n"
                            "    COUNTIF(event_name = 'refund') AS refund_event_count,\n"
                            '    SUM(gross_revenue_local) AS gross_revenue_local,\n'
                            '    SUM(refund_revenue_local) AS refund_revenue_local,\n'
                            '    SUM(net_revenue_local) AS net_revenue_local,\n'
                            '    SUM(gross_revenue_usd) AS gross_revenue_usd,\n'
                            '    SUM(refund_revenue_usd) AS refund_revenue_usd,\n'
                            '    SUM(net_revenue_usd) AS net_revenue_usd\n'
                            '  FROM `{{OUTPUT_DATASET}}.ltv_transaction_base`\n'
                            '  WHERE analysis_eligible\n'
                            '  GROUP BY user_id\n'
                            "  HAVING COUNTIF(event_name = 'purchase') > 0\n"
                            ')\n'
                            'SELECT\n'
                            '  c.user_id,\n'
                            '  c.first_purchase_date,\n'
                            '  c.last_purchase_date,\n'
                            '  DATE_TRUNC(c.first_purchase_date, MONTH) AS first_purchase_month,\n'
                            '  c.order_count,\n'
                            '  c.refund_event_count,\n'
                            '  c.order_count >= 2 AS repeat_customer,\n'
                            '  DATE_DIFF(c.last_purchase_date, c.first_purchase_date, DAY) AS '
                            'purchase_span_days,\n'
                            '  DATE_DIFF(b.data_end_date, c.first_purchase_date, DAY) AS '
                            'observed_days_since_first_purchase,\n'
                            '  DATE_DIFF(b.data_end_date, c.last_purchase_date, DAY) AS '
                            'days_since_last_purchase,\n'
                            '  c.gross_revenue_local,\n'
                            '  c.refund_revenue_local,\n'
                            '  c.net_revenue_local,\n'
                            '  SAFE_DIVIDE(c.gross_revenue_local, c.order_count) AS '
                            'average_order_value_local,\n'
                            '  c.gross_revenue_usd,\n'
                            '  c.refund_revenue_usd,\n'
                            '  c.net_revenue_usd,\n'
                            '  SAFE_DIVIDE(c.gross_revenue_usd, c.order_count) AS '
                            'average_order_value_usd,\n'
                            '  b.data_end_date AS analysis_end_date\n'
                            'FROM customer_rollup AS c\n'
                            'CROSS JOIN data_bounds AS b;\n'
                            '\n',
 '04_overall_summary.sql': 'CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_overall_summary` AS\n'
                           'WITH stats AS (\n'
                           '  SELECT\n'
                           '    COUNT(*) AS customers,\n'
                           '    SUM(order_count) AS orders,\n'
                           '    COUNTIF(repeat_customer) AS repeat_customers,\n'
                           '    COUNTIF(net_revenue_local < 0 OR net_revenue_usd < 0) AS '
                           'negative_ltv_customers,\n'
                           '    MIN(first_purchase_date) AS first_purchase_date,\n'
                           '    MAX(analysis_end_date) AS analysis_end_date,\n'
                           '    SUM(gross_revenue_local) AS gross_revenue_local,\n'
                           '    SUM(refund_revenue_local) AS refund_revenue_local,\n'
                           '    SUM(net_revenue_local) AS net_revenue_local,\n'
                           '    AVG(net_revenue_local) AS average_ltv_local,\n'
                           '    APPROX_QUANTILES(net_revenue_local, 100) AS ltv_quantiles_local,\n'
                           '    SUM(gross_revenue_usd) AS gross_revenue_usd,\n'
                           '    SUM(refund_revenue_usd) AS refund_revenue_usd,\n'
                           '    SUM(net_revenue_usd) AS net_revenue_usd,\n'
                           '    AVG(net_revenue_usd) AS average_ltv_usd,\n'
                           '    APPROX_QUANTILES(net_revenue_usd, 100) AS ltv_quantiles_usd\n'
                           '  FROM `{{OUTPUT_DATASET}}.ltv_customer_summary`\n'
                           ')\n'
                           'SELECT\n'
                           '  customers,\n'
                           '  orders,\n'
                           '  repeat_customers,\n'
                           '  negative_ltv_customers,\n'
                           '  first_purchase_date,\n'
                           '  analysis_end_date,\n'
                           '  gross_revenue_local,\n'
                           '  refund_revenue_local,\n'
                           '  net_revenue_local,\n'
                           '  average_ltv_local,\n'
                           '  ltv_quantiles_local[SAFE_OFFSET(50)] AS median_ltv_local,\n'
                           '  ltv_quantiles_local[SAFE_OFFSET(75)] AS p75_ltv_local,\n'
                           '  ltv_quantiles_local[SAFE_OFFSET(90)] AS p90_ltv_local,\n'
                           '  ltv_quantiles_local[SAFE_OFFSET(95)] AS p95_ltv_local,\n'
                           '  gross_revenue_usd,\n'
                           '  refund_revenue_usd,\n'
                           '  net_revenue_usd,\n'
                           '  average_ltv_usd,\n'
                           '  ltv_quantiles_usd[SAFE_OFFSET(50)] AS median_ltv_usd,\n'
                           '  ltv_quantiles_usd[SAFE_OFFSET(75)] AS p75_ltv_usd,\n'
                           '  ltv_quantiles_usd[SAFE_OFFSET(90)] AS p90_ltv_usd,\n'
                           '  ltv_quantiles_usd[SAFE_OFFSET(95)] AS p95_ltv_usd,\n'
                           '  SAFE_DIVIDE(repeat_customers, customers) AS repeat_customer_rate,\n'
                           '  SAFE_DIVIDE(orders, customers) AS orders_per_customer,\n'
                           '  SAFE_DIVIDE(gross_revenue_local, orders) AS '
                           'average_order_value_local,\n'
                           '  SAFE_DIVIDE(gross_revenue_usd, orders) AS average_order_value_usd,\n'
                           '  SAFE_DIVIDE(refund_revenue_local, gross_revenue_local) AS '
                           'refund_share_local,\n'
                           '  SAFE_DIVIDE(refund_revenue_usd, gross_revenue_usd) AS '
                           'refund_share_usd\n'
                           'FROM stats;\n'
                           '\n',
 '05_decile_summary.sql': 'CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_decile_summary` AS\n'
                          'WITH metric_choice AS (\n'
                          '  SELECT\n'
                          '    IF(\n'
                          '      distinct_purchase_currencies <= 1\n'
                          '        AND purchase_events_with_local_value > 0,\n'
                          "      'local',\n"
                          "      'usd'\n"
                          '    ) AS metric_basis\n'
                          '  FROM `{{OUTPUT_DATASET}}.ltv_data_quality`\n'
                          '),\n'
                          'ranked AS (\n'
                          '  SELECT\n'
                          '    c.*,\n'
                          '    NTILE(10) OVER (\n'
                          '      ORDER BY\n'
                          "        IF(m.metric_basis = 'local', c.net_revenue_local, "
                          'c.net_revenue_usd) DESC,\n'
                          '        c.user_id\n'
                          '    ) AS ltv_decile\n'
                          '  FROM `{{OUTPUT_DATASET}}.ltv_customer_summary` AS c\n'
                          '  CROSS JOIN metric_choice AS m\n'
                          '),\n'
                          'aggregated AS (\n'
                          '  SELECT\n'
                          '    ltv_decile,\n'
                          '    COUNT(*) AS customers,\n'
                          '    SUM(order_count) AS orders,\n'
                          '    SUM(net_revenue_local) AS net_revenue_local,\n'
                          '    AVG(net_revenue_local) AS average_ltv_local,\n'
                          '    MIN(net_revenue_local) AS minimum_ltv_local,\n'
                          '    MAX(net_revenue_local) AS maximum_ltv_local,\n'
                          '    SUM(net_revenue_usd) AS net_revenue_usd,\n'
                          '    AVG(net_revenue_usd) AS average_ltv_usd,\n'
                          '    MIN(net_revenue_usd) AS minimum_ltv_usd,\n'
                          '    MAX(net_revenue_usd) AS maximum_ltv_usd,\n'
                          '    SUM(GREATEST(net_revenue_local, 0)) AS positive_net_revenue_local,\n'
                          '    SUM(GREATEST(net_revenue_usd, 0)) AS positive_net_revenue_usd,\n'
                          '    SAFE_DIVIDE(COUNTIF(repeat_customer), COUNT(*)) AS '
                          'repeat_customer_rate\n'
                          '  FROM ranked\n'
                          '  GROUP BY ltv_decile\n'
                          '),\n'
                          'totals AS (\n'
                          '  SELECT\n'
                          '    SUM(customers) AS customers,\n'
                          '    SUM(positive_net_revenue_local) AS positive_net_revenue_local,\n'
                          '    SUM(positive_net_revenue_usd) AS positive_net_revenue_usd\n'
                          '  FROM aggregated\n'
                          ')\n'
                          'SELECT\n'
                          '  a.*,\n'
                          '  SAFE_DIVIDE(a.customers, t.customers) AS customer_share,\n'
                          '  SAFE_DIVIDE(a.positive_net_revenue_local, '
                          't.positive_net_revenue_local) AS positive_revenue_share_local,\n'
                          '  SAFE_DIVIDE(a.positive_net_revenue_usd, t.positive_net_revenue_usd) '
                          'AS positive_revenue_share_usd,\n'
                          '  SAFE_DIVIDE(\n'
                          '    SUM(a.customers) OVER (ORDER BY a.ltv_decile),\n'
                          '    t.customers\n'
                          '  ) AS cumulative_customer_share,\n'
                          '  SAFE_DIVIDE(\n'
                          '    SUM(a.positive_net_revenue_local) OVER (ORDER BY a.ltv_decile),\n'
                          '    t.positive_net_revenue_local\n'
                          '  ) AS cumulative_positive_revenue_share_local,\n'
                          '  SAFE_DIVIDE(\n'
                          '    SUM(a.positive_net_revenue_usd) OVER (ORDER BY a.ltv_decile),\n'
                          '    t.positive_net_revenue_usd\n'
                          '  ) AS cumulative_positive_revenue_share_usd\n'
                          'FROM aggregated AS a\n'
                          'CROSS JOIN totals AS t\n'
                          'ORDER BY a.ltv_decile;\n',
 '06_percentile_distribution.sql': 'CREATE OR REPLACE TABLE '
                                   '`{{OUTPUT_DATASET}}.ltv_percentile_distribution` AS\n'
                                   'WITH metric_choice AS (\n'
                                   '  SELECT\n'
                                   '    IF(\n'
                                   '      distinct_purchase_currencies <= 1\n'
                                   '        AND purchase_events_with_local_value > 0,\n'
                                   "      'local',\n"
                                   "      'usd'\n"
                                   '    ) AS metric_basis\n'
                                   '  FROM `{{OUTPUT_DATASET}}.ltv_data_quality`\n'
                                   '),\n'
                                   'ranked AS (\n'
                                   '  SELECT\n'
                                   '    c.*,\n'
                                   '    NTILE(100) OVER (\n'
                                   '      ORDER BY\n'
                                   "        IF(m.metric_basis = 'local', c.net_revenue_local, "
                                   'c.net_revenue_usd) DESC,\n'
                                   '        c.user_id\n'
                                   '    ) AS ltv_percentile\n'
                                   '  FROM `{{OUTPUT_DATASET}}.ltv_customer_summary` AS c\n'
                                   '  CROSS JOIN metric_choice AS m\n'
                                   '),\n'
                                   'aggregated AS (\n'
                                   '  SELECT\n'
                                   '    ltv_percentile,\n'
                                   '    COUNT(*) AS customers,\n'
                                   '    SUM(GREATEST(net_revenue_local, 0)) AS '
                                   'positive_net_revenue_local,\n'
                                   '    SUM(GREATEST(net_revenue_usd, 0)) AS '
                                   'positive_net_revenue_usd,\n'
                                   '    AVG(net_revenue_local) AS average_ltv_local,\n'
                                   '    AVG(net_revenue_usd) AS average_ltv_usd\n'
                                   '  FROM ranked\n'
                                   '  GROUP BY ltv_percentile\n'
                                   '),\n'
                                   'totals AS (\n'
                                   '  SELECT\n'
                                   '    SUM(customers) AS customers,\n'
                                   '    SUM(positive_net_revenue_local) AS '
                                   'positive_net_revenue_local,\n'
                                   '    SUM(positive_net_revenue_usd) AS positive_net_revenue_usd\n'
                                   '  FROM aggregated\n'
                                   ')\n'
                                   'SELECT\n'
                                   '  a.*,\n'
                                   '  SAFE_DIVIDE(\n'
                                   '    SUM(a.customers) OVER (ORDER BY a.ltv_percentile),\n'
                                   '    t.customers\n'
                                   '  ) AS cumulative_customer_share,\n'
                                   '  SAFE_DIVIDE(\n'
                                   '    SUM(a.positive_net_revenue_local) OVER (ORDER BY '
                                   'a.ltv_percentile),\n'
                                   '    t.positive_net_revenue_local\n'
                                   '  ) AS cumulative_positive_revenue_share_local,\n'
                                   '  SAFE_DIVIDE(\n'
                                   '    SUM(a.positive_net_revenue_usd) OVER (ORDER BY '
                                   'a.ltv_percentile),\n'
                                   '    t.positive_net_revenue_usd\n'
                                   '  ) AS cumulative_positive_revenue_share_usd\n'
                                   'FROM aggregated AS a\n'
                                   'CROSS JOIN totals AS t\n'
                                   'ORDER BY a.ltv_percentile;\n',
 '07_cohort_summary.sql': 'CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_cohort_summary`\n'
                          'PARTITION BY cohort_month AS\n'
                          'WITH cohort_rollup AS (\n'
                          '  SELECT\n'
                          '    first_purchase_month AS cohort_month,\n'
                          '    COUNT(*) AS cohort_size,\n'
                          '    SUM(order_count) AS orders,\n'
                          '    COUNTIF(repeat_customer) AS repeat_customers,\n'
                          '    AVG(observed_days_since_first_purchase) AS '
                          'average_observation_days,\n'
                          '    SUM(gross_revenue_local) AS gross_revenue_local,\n'
                          '    SUM(refund_revenue_local) AS refund_revenue_local,\n'
                          '    SUM(net_revenue_local) AS net_revenue_local,\n'
                          '    AVG(net_revenue_local) AS average_ltv_local,\n'
                          '    APPROX_QUANTILES(net_revenue_local, 100)[SAFE_OFFSET(50)] AS '
                          'median_ltv_local,\n'
                          '    SUM(gross_revenue_usd) AS gross_revenue_usd,\n'
                          '    SUM(refund_revenue_usd) AS refund_revenue_usd,\n'
                          '    SUM(net_revenue_usd) AS net_revenue_usd,\n'
                          '    AVG(net_revenue_usd) AS average_ltv_usd,\n'
                          '    APPROX_QUANTILES(net_revenue_usd, 100)[SAFE_OFFSET(50)] AS '
                          'median_ltv_usd\n'
                          '  FROM `{{OUTPUT_DATASET}}.ltv_customer_summary`\n'
                          '  GROUP BY first_purchase_month\n'
                          ')\n'
                          'SELECT\n'
                          '  *,\n'
                          '  SAFE_DIVIDE(orders, cohort_size) AS orders_per_customer,\n'
                          '  SAFE_DIVIDE(repeat_customers, cohort_size) AS repeat_customer_rate,\n'
                          '  SAFE_DIVIDE(gross_revenue_local, orders) AS '
                          'average_order_value_local,\n'
                          '  SAFE_DIVIDE(gross_revenue_usd, orders) AS average_order_value_usd,\n'
                          '  SAFE_DIVIDE(refund_revenue_local, gross_revenue_local) AS '
                          'refund_share_local,\n'
                          '  SAFE_DIVIDE(refund_revenue_usd, gross_revenue_usd) AS '
                          'refund_share_usd\n'
                          'FROM cohort_rollup\n'
                          'ORDER BY cohort_month;\n',
 '08_monthly_metrics.sql': 'CREATE OR REPLACE TABLE `{{OUTPUT_DATASET}}.ltv_monthly_metrics`\n'
                           'PARTITION BY month AS\n'
                           'WITH raw AS (\n'
                           '  SELECT\n'
                           "    PARSE_DATE('%Y%m%d', event_date) AS event_day,\n"
                           "    DATE_TRUNC(PARSE_DATE('%Y%m%d', event_date), MONTH) AS month,\n"
                           '    user_id,\n'
                           '    user_pseudo_id,\n'
                           '    event_name,\n'
                           '    is_active_user,\n'
                           '    event_timestamp,\n'
                           '    event_bundle_sequence_id,\n'
                           '    event_server_timestamp_offset,\n'
                           "    NULLIF(TRIM(ecommerce.transaction_id), '') AS "
                           'source_transaction_id,\n'
                           '    SAFE_CAST(ecommerce.purchase_revenue AS FLOAT64) AS '
                           'purchase_revenue_local,\n'
                           '    SAFE_CAST(ecommerce.purchase_revenue_in_usd AS FLOAT64) AS '
                           'purchase_revenue_usd,\n'
                           '    SAFE_CAST(ecommerce.refund_value AS FLOAT64) AS '
                           'refund_value_local,\n'
                           '    SAFE_CAST(ecommerce.refund_value_in_usd AS FLOAT64) AS '
                           'refund_value_usd,\n'
                           '    SAFE_CAST(ecommerce.total_item_quantity AS FLOAT64) AS '
                           'total_item_quantity,\n'
                           '    (\n'
                           '      SELECT ep.value.int_value\n'
                           '      FROM UNNEST(event_params) AS ep\n'
                           "      WHERE ep.key = 'ga_session_id'\n"
                           '      LIMIT 1\n'
                           '    ) AS ga_session_id,\n'
                           '    COALESCE(\n'
                           '      (\n'
                           '        SELECT ep.value.int_value\n'
                           '        FROM UNNEST(event_params) AS ep\n'
                           "        WHERE ep.key = 'session_engaged'\n"
                           '        LIMIT 1\n'
                           '      ),\n'
                           '      SAFE_CAST(\n'
                           '        (\n'
                           '          SELECT ep.value.string_value\n'
                           '          FROM UNNEST(event_params) AS ep\n'
                           "          WHERE ep.key = 'session_engaged'\n"
                           '          LIMIT 1\n'
                           '        ) AS INT64\n'
                           '      ),\n'
                           '      0\n'
                           '    ) = 1 AS session_engaged\n'
                           '  FROM `{{SOURCE_TABLE}}`\n'
                           '  WHERE {{DAILY_TABLE_FILTER}}\n'
                           '),\n'
                           'events AS (\n'
                           '  SELECT\n'
                           '    *,\n'
                           '    IF(\n'
                           '      user_pseudo_id IS NULL OR ga_session_id IS NULL,\n'
                           '      NULL,\n'
                           "      CONCAT(user_pseudo_id, '-', CAST(ga_session_id AS STRING))\n"
                           '    ) AS session_key,\n'
                           '    CASE\n'
                           "      WHEN user_id IS NOT NULL THEN CONCAT('u:', user_id)\n"
                           "      WHEN user_pseudo_id IS NOT NULL THEN CONCAT('p:', "
                           'user_pseudo_id)\n'
                           '      ELSE NULL\n'
                           '    END AS analytics_user_key\n'
                           '  FROM raw\n'
                           '),\n'
                           'event_metrics AS (\n'
                           '  SELECT\n'
                           '    month,\n'
                           '    MIN(event_day) AS observed_start_date,\n'
                           '    MAX(event_day) AS observed_end_date,\n'
                           '    COUNT(DISTINCT event_day) AS observed_event_days,\n'
                           '    COUNT(DISTINCT event_day) = EXTRACT(DAY FROM LAST_DAY(month))\n'
                           '      AND MIN(event_day) = month\n'
                           '      AND MAX(event_day) = LAST_DAY(month) AS is_complete_month,\n'
                           '    COUNT(*) AS events,\n'
                           '    COUNT(DISTINCT analytics_user_key) AS total_users,\n'
                           '    COUNT(\n'
                           '      DISTINCT IF(\n'
                           '        COALESCE(is_active_user, FALSE) OR event_name = '
                           "'user_engagement',\n"
                           '        analytics_user_key,\n'
                           '        NULL\n'
                           '      )\n'
                           '    ) AS active_users,\n'
                           '    COUNT(DISTINCT user_id) AS identified_users,\n'
                           "    COUNT(DISTINCT IF(event_name IN ('first_visit', 'first_open'), "
                           'analytics_user_key, NULL)) AS new_users,\n'
                           '    COUNT(DISTINCT session_key) AS sessions,\n'
                           '    COUNT(DISTINCT IF(session_engaged, session_key, NULL)) AS '
                           'engaged_sessions,\n'
                           "    COUNT(DISTINCT IF(event_name = 'view_item', analytics_user_key, "
                           'NULL)) AS view_item_users,\n'
                           "    COUNT(DISTINCT IF(event_name = 'add_to_cart', analytics_user_key, "
                           'NULL)) AS add_to_cart_users,\n'
                           "    COUNT(DISTINCT IF(event_name = 'begin_checkout', "
                           'analytics_user_key, NULL)) AS begin_checkout_users,\n'
                           "    COUNT(DISTINCT IF(event_name = 'purchase', analytics_user_key, "
                           'NULL)) AS purchase_users,\n'
                           "    COUNT(DISTINCT IF(event_name = 'view_item', session_key, NULL)) AS "
                           'view_item_sessions,\n'
                           "    COUNT(DISTINCT IF(event_name = 'add_to_cart', session_key, NULL)) "
                           'AS add_to_cart_sessions,\n'
                           "    COUNT(DISTINCT IF(event_name = 'begin_checkout', session_key, "
                           'NULL)) AS begin_checkout_sessions,\n'
                           "    COUNT(DISTINCT IF(event_name = 'purchase', session_key, NULL)) AS "
                           'purchase_sessions\n'
                           '  FROM events\n'
                           '  GROUP BY month\n'
                           '),\n'
                           'commerce_keyed AS (\n'
                           '  SELECT\n'
                           '    *,\n'
                           '    CASE\n'
                           "      WHEN event_name = 'purchase' AND source_transaction_id IS NOT "
                           'NULL THEN\n'
                           "        CONCAT('purchase|', COALESCE(analytics_user_key, "
                           "'__unknown__'), '|', source_transaction_id)\n"
                           "      WHEN event_name = 'refund' AND source_transaction_id IS NOT NULL "
                           'THEN\n'
                           '        CONCAT(\n'
                           "          'refund|', COALESCE(analytics_user_key, '__unknown__'), '|', "
                           'source_transaction_id,\n'
                           "          '|', CAST(event_timestamp AS STRING),\n"
                           "          '|', CAST(COALESCE(refund_value_usd, refund_value_local, 0) "
                           'AS STRING)\n'
                           '        )\n'
                           '      ELSE\n'
                           '        CONCAT(\n'
                           "          event_name, '|', COALESCE(analytics_user_key, "
                           "'__unknown__'),\n"
                           "          '|', CAST(event_timestamp AS STRING),\n"
                           "          '|', CAST(COALESCE(event_bundle_sequence_id, -1) AS STRING)\n"
                           '        )\n'
                           '    END AS deduplication_key\n'
                           '  FROM events\n'
                           "  WHERE event_name IN ('purchase', 'refund')\n"
                           '),\n'
                           'commerce AS (\n'
                           '  SELECT * EXCEPT(deduplication_rank)\n'
                           '  FROM (\n'
                           '    SELECT\n'
                           '      *,\n'
                           '      ROW_NUMBER() OVER (\n'
                           '        PARTITION BY deduplication_key\n'
                           '        ORDER BY COALESCE(event_server_timestamp_offset, 0) DESC, '
                           'event_timestamp DESC\n'
                           '      ) AS deduplication_rank\n'
                           '    FROM commerce_keyed\n'
                           '  )\n'
                           '  WHERE deduplication_rank = 1\n'
                           '),\n'
                           'purchaser_month AS (\n'
                           '  SELECT\n'
                           '    month,\n'
                           '    analytics_user_key,\n'
                           "    COUNTIF(event_name = 'purchase') AS orders\n"
                           '  FROM commerce\n'
                           '  WHERE analytics_user_key IS NOT NULL\n'
                           '  GROUP BY month, analytics_user_key\n'
                           "  HAVING COUNTIF(event_name = 'purchase') > 0\n"
                           '),\n'
                           'repeat_metrics AS (\n'
                           '  SELECT\n'
                           '    month,\n'
                           '    COUNT(*) AS purchasers,\n'
                           '    COUNTIF(orders >= 2) AS repeat_purchasers\n'
                           '  FROM purchaser_month\n'
                           '  GROUP BY month\n'
                           '),\n'
                           'first_purchase AS (\n'
                           '  SELECT\n'
                           '    analytics_user_key,\n'
                           '    MIN(month) AS first_purchase_month\n'
                           '  FROM commerce\n'
                           "  WHERE event_name = 'purchase'\n"
                           '    AND analytics_user_key IS NOT NULL\n'
                           '  GROUP BY analytics_user_key\n'
                           '),\n'
                           'new_purchaser_metrics AS (\n'
                           '  SELECT\n'
                           '    first_purchase_month AS month,\n'
                           '    COUNT(*) AS new_purchasers\n'
                           '  FROM first_purchase\n'
                           '  GROUP BY first_purchase_month\n'
                           '),\n'
                           'commerce_metrics AS (\n'
                           '  SELECT\n'
                           '    month,\n'
                           "    COUNTIF(event_name = 'purchase') AS orders,\n"
                           "    COUNTIF(event_name = 'refund') AS refund_events,\n"
                           "    COUNT(DISTINCT IF(event_name = 'purchase', analytics_user_key, "
                           'NULL)) AS purchasers,\n'
                           "    COUNT(DISTINCT IF(event_name = 'purchase', user_id, NULL)) AS "
                           'identified_purchasers,\n'
                           "    SUM(IF(event_name = 'purchase', COALESCE(total_item_quantity, 0), "
                           '0)) AS items_purchased,\n'
                           "    SUM(IF(event_name = 'purchase', COALESCE(purchase_revenue_local, "
                           '0), 0)) AS gross_revenue_local,\n'
                           "    SUM(IF(event_name = 'refund', COALESCE(refund_value_local, 0), 0)) "
                           'AS refund_revenue_local,\n'
                           "    SUM(IF(event_name = 'purchase', COALESCE(purchase_revenue_local, "
                           '0), 0))\n'
                           "      - SUM(IF(event_name = 'refund', COALESCE(refund_value_local, 0), "
                           '0)) AS net_revenue_local,\n'
                           "    SUM(IF(event_name = 'purchase', COALESCE(purchase_revenue_usd, 0), "
                           '0)) AS gross_revenue_usd,\n'
                           "    SUM(IF(event_name = 'refund', COALESCE(refund_value_usd, 0), 0)) "
                           'AS refund_revenue_usd,\n'
                           "    SUM(IF(event_name = 'purchase', COALESCE(purchase_revenue_usd, 0), "
                           '0))\n'
                           "      - SUM(IF(event_name = 'refund', COALESCE(refund_value_usd, 0), "
                           '0)) AS net_revenue_usd\n'
                           '  FROM commerce\n'
                           '  GROUP BY month\n'
                           '),\n'
                           'combined AS (\n'
                           '  SELECT\n'
                           '    e.*,\n'
                           '    COALESCE(c.orders, 0) AS orders,\n'
                           '    COALESCE(c.refund_events, 0) AS refund_events,\n'
                           '    COALESCE(c.purchasers, 0) AS purchasers,\n'
                           '    COALESCE(c.identified_purchasers, 0) AS identified_purchasers,\n'
                           '    COALESCE(r.repeat_purchasers, 0) AS repeat_purchasers,\n'
                           '    COALESCE(n.new_purchasers, 0) AS new_purchasers,\n'
                           '    COALESCE(c.items_purchased, 0) AS items_purchased,\n'
                           '    COALESCE(c.gross_revenue_local, 0) AS gross_revenue_local,\n'
                           '    COALESCE(c.refund_revenue_local, 0) AS refund_revenue_local,\n'
                           '    COALESCE(c.net_revenue_local, 0) AS net_revenue_local,\n'
                           '    COALESCE(c.gross_revenue_usd, 0) AS gross_revenue_usd,\n'
                           '    COALESCE(c.refund_revenue_usd, 0) AS refund_revenue_usd,\n'
                           '    COALESCE(c.net_revenue_usd, 0) AS net_revenue_usd\n'
                           '  FROM event_metrics AS e\n'
                           '  LEFT JOIN commerce_metrics AS c USING (month)\n'
                           '  LEFT JOIN repeat_metrics AS r USING (month)\n'
                           '  LEFT JOIN new_purchaser_metrics AS n USING (month)\n'
                           ')\n'
                           'SELECT\n'
                           '  *,\n'
                           '  SAFE_DIVIDE(engaged_sessions, sessions) AS engagement_rate,\n'
                           '  1 - SAFE_DIVIDE(engaged_sessions, sessions) AS bounce_rate,\n'
                           '  SAFE_DIVIDE(new_users, active_users) AS new_user_rate,\n'
                           '  SAFE_DIVIDE(sessions, active_users) AS sessions_per_active_user,\n'
                           '  SAFE_DIVIDE(events, active_users) AS events_per_active_user,\n'
                           '  SAFE_DIVIDE(purchasers, active_users) AS purchaser_rate,\n'
                           '  SAFE_DIVIDE(identified_purchasers, identified_users) AS '
                           'identified_purchaser_rate,\n'
                           '  SAFE_DIVIDE(purchase_sessions, sessions) AS purchase_session_rate,\n'
                           '  SAFE_DIVIDE(view_item_sessions, sessions) AS '
                           'view_item_session_rate,\n'
                           '  SAFE_DIVIDE(add_to_cart_sessions, sessions) AS '
                           'add_to_cart_session_rate,\n'
                           '  SAFE_DIVIDE(begin_checkout_sessions, sessions) AS '
                           'begin_checkout_session_rate,\n'
                           '  SAFE_DIVIDE(add_to_cart_users, view_item_users) AS '
                           'view_to_cart_user_rate,\n'
                           '  SAFE_DIVIDE(begin_checkout_users, add_to_cart_users) AS '
                           'cart_to_checkout_user_rate,\n'
                           '  SAFE_DIVIDE(purchase_users, begin_checkout_users) AS '
                           'checkout_to_purchase_user_rate,\n'
                           '  SAFE_DIVIDE(purchase_users, view_item_users) AS '
                           'purchase_to_view_user_rate,\n'
                           '  SAFE_DIVIDE(orders, purchasers) AS purchase_frequency,\n'
                           '  SAFE_DIVIDE(repeat_purchasers, purchasers) AS '
                           'repeat_purchaser_rate,\n'
                           '  SAFE_DIVIDE(new_purchasers, purchasers) AS new_purchaser_rate,\n'
                           '  SAFE_DIVIDE(items_purchased, orders) AS items_per_order,\n'
                           '  SAFE_DIVIDE(gross_revenue_local, orders) AS '
                           'average_order_value_local,\n'
                           '  SAFE_DIVIDE(net_revenue_local, orders) AS '
                           'net_average_order_value_local,\n'
                           '  SAFE_DIVIDE(net_revenue_local, active_users) AS '
                           'ecommerce_arpu_local,\n'
                           '  SAFE_DIVIDE(net_revenue_local, purchasers) AS '
                           'ecommerce_arppu_local,\n'
                           '  SAFE_DIVIDE(net_revenue_local, sessions) AS '
                           'revenue_per_session_local,\n'
                           '  SAFE_DIVIDE(refund_revenue_local, gross_revenue_local) AS '
                           'refund_value_share_local,\n'
                           '  SAFE_DIVIDE(gross_revenue_usd, orders) AS average_order_value_usd,\n'
                           '  SAFE_DIVIDE(net_revenue_usd, orders) AS '
                           'net_average_order_value_usd,\n'
                           '  SAFE_DIVIDE(net_revenue_usd, active_users) AS ecommerce_arpu_usd,\n'
                           '  SAFE_DIVIDE(net_revenue_usd, purchasers) AS ecommerce_arppu_usd,\n'
                           '  SAFE_DIVIDE(net_revenue_usd, sessions) AS revenue_per_session_usd,\n'
                           '  SAFE_DIVIDE(refund_revenue_usd, gross_revenue_usd) AS '
                           'refund_value_share_usd,\n'
                           '  SAFE_DIVIDE(refund_events, orders) AS refund_event_rate\n'
                           'FROM combined\n'
                           'ORDER BY month;\n',
 '09_monthly_metric_changes.sql': 'CREATE OR REPLACE TABLE '
                                  '`{{OUTPUT_DATASET}}.ltv_monthly_metric_changes`\n'
                                  'PARTITION BY month AS\n'
                                  'WITH metric_choice AS (\n'
                                  '  SELECT\n'
                                  '    IF(\n'
                                  '      distinct_purchase_currencies <= 1\n'
                                  '        AND purchase_events_with_local_value > 0,\n'
                                  "      'local',\n"
                                  "      'usd'\n"
                                  '    ) AS metric_basis,\n'
                                  '    IF(\n'
                                  '      distinct_purchase_currencies <= 1\n'
                                  '        AND purchase_events_with_local_value > 0,\n'
                                  "      COALESCE(purchase_currencies[SAFE_OFFSET(0)], 'LOCAL'),\n"
                                  "      'USD'\n"
                                  '    ) AS currency\n'
                                  '  FROM `{{OUTPUT_DATASET}}.ltv_data_quality`\n'
                                  '),\n'
                                  'long_metrics AS (\n'
                                  '  SELECT\n'
                                  '    m.month,\n'
                                  '    m.observed_start_date,\n'
                                  '    m.observed_end_date,\n'
                                  '    m.observed_event_days,\n'
                                  '    m.is_complete_month,\n'
                                  '    choice.metric_basis,\n'
                                  '    choice.currency,\n'
                                  '    metric.display_order,\n'
                                  '    metric.metric_group,\n'
                                  '    metric.metric_name,\n'
                                  '    metric.metric_label,\n'
                                  '    metric.metric_unit,\n'
                                  '    metric.metric_value\n'
                                  '  FROM `{{OUTPUT_DATASET}}.ltv_monthly_metrics` AS m\n'
                                  '  CROSS JOIN metric_choice AS choice\n'
                                  '  CROSS JOIN UNNEST([\n'
                                  "    STRUCT(1 AS display_order, 'Kitle' AS metric_group, "
                                  "'active_users' AS metric_name, 'Aktif kullanıcı' AS "
                                  "metric_label, 'count' AS metric_unit, CAST(m.active_users AS "
                                  'FLOAT64) AS metric_value),\n'
                                  "    STRUCT(2, 'Kitle', 'new_users', 'Yeni kullanıcı', 'count', "
                                  'CAST(m.new_users AS FLOAT64)),\n'
                                  "    STRUCT(3, 'Kitle', 'sessions', 'Oturum', 'count', "
                                  'CAST(m.sessions AS FLOAT64)),\n'
                                  "    STRUCT(4, 'Kitle', 'engagement_rate', 'Etkileşim oranı', "
                                  "'ratio', CAST(m.engagement_rate AS FLOAT64)),\n"
                                  "    STRUCT(5, 'Kitle', 'sessions_per_active_user', 'Aktif "
                                  "kullanıcı başına oturum', 'number', "
                                  'CAST(m.sessions_per_active_user AS FLOAT64)),\n'
                                  "    STRUCT(10, 'Ticaret', 'purchasers', 'Satın alan kullanıcı', "
                                  "'count', CAST(m.purchasers AS FLOAT64)),\n"
                                  "    STRUCT(11, 'Ticaret', 'orders', 'Sipariş', 'count', "
                                  'CAST(m.orders AS FLOAT64)),\n'
                                  "    STRUCT(12, 'Ticaret', 'purchase_frequency', 'Satın alma "
                                  "sıklığı', 'number', CAST(m.purchase_frequency AS FLOAT64)),\n"
                                  "    STRUCT(13, 'Ticaret', 'items_per_order', 'Sipariş başına "
                                  "ürün', 'number', CAST(m.items_per_order AS FLOAT64)),\n"
                                  "    STRUCT(14, 'Ticaret', 'repeat_purchaser_rate', 'Aylık "
                                  "tekrar satın alan oranı', 'ratio', CAST(m.repeat_purchaser_rate "
                                  'AS FLOAT64)),\n'
                                  "    STRUCT(15, 'Ticaret', 'new_purchaser_rate', 'Yeni satın "
                                  "alan oranı', 'ratio', CAST(m.new_purchaser_rate AS FLOAT64)),\n"
                                  "    STRUCT(20, 'Gelir', 'gross_revenue', 'Brüt satın alma "
                                  "geliri', 'currency', CAST(IF(choice.metric_basis = 'local', "
                                  'm.gross_revenue_local, m.gross_revenue_usd) AS FLOAT64)),\n'
                                  "    STRUCT(21, 'Gelir', 'net_revenue', 'Net satın alma geliri', "
                                  "'currency', CAST(IF(choice.metric_basis = 'local', "
                                  'm.net_revenue_local, m.net_revenue_usd) AS FLOAT64)),\n'
                                  "    STRUCT(22, 'Gelir', 'aov', 'Ortalama sipariş tutarı (AOV)', "
                                  "'currency', CAST(IF(choice.metric_basis = 'local', "
                                  'm.average_order_value_local, m.average_order_value_usd) AS '
                                  'FLOAT64)),\n'
                                  "    STRUCT(23, 'Gelir', 'net_aov', 'Net ortalama sipariş "
                                  "tutarı', 'currency', CAST(IF(choice.metric_basis = 'local', "
                                  'm.net_average_order_value_local, m.net_average_order_value_usd) '
                                  'AS FLOAT64)),\n'
                                  "    STRUCT(24, 'Gelir', 'ecommerce_arpu', 'E-ticaret ARPU', "
                                  "'currency', CAST(IF(choice.metric_basis = 'local', "
                                  'm.ecommerce_arpu_local, m.ecommerce_arpu_usd) AS FLOAT64)),\n'
                                  "    STRUCT(25, 'Gelir', 'ecommerce_arppu', 'E-ticaret ARPPU', "
                                  "'currency', CAST(IF(choice.metric_basis = 'local', "
                                  'm.ecommerce_arppu_local, m.ecommerce_arppu_usd) AS FLOAT64)),\n'
                                  "    STRUCT(26, 'Gelir', 'revenue_per_session', 'Oturum başına "
                                  "gelir', 'currency', CAST(IF(choice.metric_basis = 'local', "
                                  'm.revenue_per_session_local, m.revenue_per_session_usd) AS '
                                  'FLOAT64)),\n'
                                  "    STRUCT(30, 'Dönüşüm', 'purchaser_rate', 'Satın alan "
                                  "kullanıcı oranı', 'ratio', CAST(m.purchaser_rate AS FLOAT64)),\n"
                                  "    STRUCT(31, 'Dönüşüm', 'purchase_session_rate', 'Oturum "
                                  "satın alma oranı', 'ratio', CAST(m.purchase_session_rate AS "
                                  'FLOAT64)),\n'
                                  "    STRUCT(32, 'Dönüşüm', 'view_to_cart_user_rate', 'Ürün "
                                  "görüntülemeden sepete geçiş', 'ratio', "
                                  'CAST(m.view_to_cart_user_rate AS FLOAT64)),\n'
                                  "    STRUCT(33, 'Dönüşüm', 'cart_to_checkout_user_rate', "
                                  "'Sepetten ödeme başlangıcına geçiş', 'ratio', "
                                  'CAST(m.cart_to_checkout_user_rate AS FLOAT64)),\n'
                                  "    STRUCT(34, 'Dönüşüm', 'checkout_to_purchase_user_rate', "
                                  "'Ödeme başlangıcından satın almaya geçiş', 'ratio', "
                                  'CAST(m.checkout_to_purchase_user_rate AS FLOAT64)),\n'
                                  "    STRUCT(35, 'Dönüşüm', 'purchase_to_view_user_rate', 'Ürün "
                                  "görüntülemeden satın almaya geçiş', 'ratio', "
                                  'CAST(m.purchase_to_view_user_rate AS FLOAT64)),\n'
                                  "    STRUCT(40, 'Kalite', 'refund_value_share', 'İade tutarı "
                                  "payı', 'ratio', CAST(IF(choice.metric_basis = 'local', "
                                  'm.refund_value_share_local, m.refund_value_share_usd) AS '
                                  'FLOAT64)),\n'
                                  "    STRUCT(41, 'Kalite', 'refund_event_rate', 'Sipariş başına "
                                  "iade olayı', 'ratio', CAST(m.refund_event_rate AS FLOAT64))\n"
                                  '  ]) AS metric\n'
                                  '),\n'
                                  'changes AS (\n'
                                  '  SELECT\n'
                                  '    current.*,\n'
                                  '    previous.metric_value AS previous_month_value,\n'
                                  '    previous.is_complete_month AS previous_month_is_complete,\n'
                                  '    previous_year.metric_value AS previous_year_value,\n'
                                  '    previous_year.is_complete_month AS '
                                  'previous_year_is_complete\n'
                                  '  FROM long_metrics AS current\n'
                                  '  LEFT JOIN long_metrics AS previous\n'
                                  '    ON current.metric_name = previous.metric_name\n'
                                  '   AND previous.month = DATE_SUB(current.month, INTERVAL 1 '
                                  'MONTH)\n'
                                  '  LEFT JOIN long_metrics AS previous_year\n'
                                  '    ON current.metric_name = previous_year.metric_name\n'
                                  '   AND previous_year.month = DATE_SUB(current.month, INTERVAL 1 '
                                  'YEAR)\n'
                                  ')\n'
                                  'SELECT\n'
                                  '  *,\n'
                                  '  IF(\n'
                                  '    is_complete_month AND COALESCE(previous_month_is_complete, '
                                  'FALSE),\n'
                                  '    metric_value - previous_month_value,\n'
                                  '    NULL\n'
                                  '  ) AS mom_absolute_change,\n'
                                  '  IF(\n'
                                  '    is_complete_month AND COALESCE(previous_month_is_complete, '
                                  'FALSE),\n'
                                  '    SAFE_DIVIDE(metric_value - previous_month_value, '
                                  'ABS(previous_month_value)),\n'
                                  '    NULL\n'
                                  '  ) AS mom_change_pct,\n'
                                  '  IF(\n'
                                  '    is_complete_month AND COALESCE(previous_year_is_complete, '
                                  'FALSE),\n'
                                  '    metric_value - previous_year_value,\n'
                                  '    NULL\n'
                                  '  ) AS yoy_absolute_change,\n'
                                  '  IF(\n'
                                  '    is_complete_month AND COALESCE(previous_year_is_complete, '
                                  'FALSE),\n'
                                  '    SAFE_DIVIDE(metric_value - previous_year_value, '
                                  'ABS(previous_year_value)),\n'
                                  '    NULL\n'
                                  '  ) AS yoy_change_pct\n'
                                  'FROM changes\n'
                                  'ORDER BY month, display_order;\n'}


class LTVAnalyzer:
    """Observed customer LTV analysis for a GA4 BigQuery export.

    The public constructor intentionally has the same four business inputs as
    the churn notebook architecture. No threshold, prediction horizon or model
    setting is required. The analysis uses logged-in ``user_id`` values and
    observed purchase/refund events.
    """

    _BASE_TABLE = "ltv_transaction_base"
    _QUALITY_TABLE = "ltv_data_quality"
    _CUSTOMER_TABLE = "ltv_customer_summary"
    _SUMMARY_TABLE = "ltv_overall_summary"
    _DECILE_TABLE = "ltv_decile_summary"
    _PERCENTILE_TABLE = "ltv_percentile_distribution"
    _COHORT_TABLE = "ltv_cohort_summary"
    _MONTHLY_TABLE = "ltv_monthly_metrics"
    _MONTHLY_CHANGES_TABLE = "ltv_monthly_metric_changes"

    def __init__(
        self,
        project_id: str,
        dataset_id: str,
        table_id: str,
        output_dataset_id: str,
    ) -> None:
        self.project_id = project_id.strip()
        self.dataset_id = dataset_id.strip()
        self.table_id = table_id.strip()
        self.output_dataset_id = output_dataset_id.strip()
        self._validate_identifiers()
        self.client = bigquery.Client(project=self.project_id)

    def __repr__(self) -> str:
        return (
            "LTVAnalyzer("
            f"source='{self.project_id}.{self.dataset_id}.{self.table_id}', "
            f"output='{self.project_id}.{self.output_dataset_id}'"
            ")"
        )

    @property
    def source_table(self) -> str:
        return f"{self.project_id}.{self.dataset_id}.{self.table_id}"

    @property
    def output_dataset(self) -> str:
        return f"{self.project_id}.{self.output_dataset_id}"

    @property
    def output_tables(self) -> dict[str, str]:
        names = {
            "transactions": self._BASE_TABLE,
            "data_quality": self._QUALITY_TABLE,
            "customers": self._CUSTOMER_TABLE,
            "summary": self._SUMMARY_TABLE,
            "deciles": self._DECILE_TABLE,
            "percentiles": self._PERCENTILE_TABLE,
            "cohorts": self._COHORT_TABLE,
            "monthly_metrics": self._MONTHLY_TABLE,
            "monthly_changes": self._MONTHLY_CHANGES_TABLE,
        }
        return {key: f"{self.output_dataset}.{value}" for key, value in names.items()}

    def _validate_identifiers(self) -> None:
        if not _PROJECT_ID.fullmatch(self.project_id):
            raise ValueError("Geçersiz project_id.")
        if not _DATASET_ID.fullmatch(self.dataset_id):
            raise ValueError("Geçersiz dataset_id.")
        if not _TABLE_ID.fullmatch(self.table_id):
            raise ValueError(
                "Geçersiz table_id. Örnek geçerli değer: events_*"
            )
        if not _DATASET_ID.fullmatch(self.output_dataset_id):
            raise ValueError("Geçersiz output_dataset_id.")

    @staticmethod
    def _read_sql(filename: str) -> str:
        try:
            return _SQL_TEMPLATES[filename]
        except KeyError as exc:
            raise FileNotFoundError(f"Bilinmeyen SQL şablonu: {filename}") from exc

    def _render_sql(self, filename: str) -> str:
        sql = self._read_sql(filename)
        table_filter = (
            "REGEXP_CONTAINS(_TABLE_SUFFIX, r'^\\d{8}$')"
            if "*" in self.table_id
            else "TRUE"
        )
        replacements = {
            "{{SOURCE_TABLE}}": self.source_table,
            "{{OUTPUT_DATASET}}": self.output_dataset,
            "{{DAILY_TABLE_FILTER}}": table_filter,
        }
        for source, target in replacements.items():
            sql = sql.replace(source, target)
        return sql

    def _table_ref(self, table_name: str) -> str:
        return f"{self.output_dataset}.{table_name}"

    def _table_exists(self, table_name: str) -> bool:
        try:
            self.client.get_table(self._table_ref(table_name))
            return True
        except NotFound:
            return False

    def _require_tables(self, *table_names: str) -> None:
        missing = [name for name in table_names if not self._table_exists(name)]
        if missing:
            raise RuntimeError(
                "Önce gerekli adımı çalıştırın. Eksik çıktı tablosu: "
                + ", ".join(missing)
            )

    def _ensure_output_dataset(self) -> str:
        source_dataset = self.client.get_dataset(
            f"{self.project_id}.{self.dataset_id}"
        )
        output = bigquery.Dataset(self.output_dataset)
        output.location = source_dataset.location
        self.client.create_dataset(output, exists_ok=True)
        return source_dataset.location

    def _query_config(self) -> bigquery.QueryJobConfig:
        return bigquery.QueryJobConfig(labels={"module": "ga4-ltv"})

    def _execute_template(self, filename: str) -> dict[str, Any]:
        sql = self._render_sql(filename)
        job = self.client.query(sql, job_config=self._query_config())
        job.result()
        return {
            "sql_file": filename,
            "job_id": job.job_id,
            "bytes_processed": int(job.total_bytes_processed or 0),
            "status": "completed",
        }

    def _query_dataframe(self, sql: str):
        import pandas as pd

        rows = self.client.query(sql, job_config=self._query_config()).result()
        records = [dict(row.items()) for row in rows]
        return pd.DataFrame(records)

    def _read_table(self, table_name: str, order_by: str | None = None):
        order_clause = f" ORDER BY {order_by}" if order_by else ""
        return self._query_dataframe(
            f"SELECT * FROM `{self._table_ref(table_name)}`{order_clause}"
        )

    def _first_row(self, table_name: str) -> dict[str, Any]:
        frame = self._read_table(table_name)
        if frame.empty:
            return {}
        return frame.iloc[0].to_dict()

    def validate(self) -> dict[str, Any]:
        """Validate source dataset and table pattern without writing data."""

        dataset = self.client.get_dataset(f"{self.project_id}.{self.dataset_id}")
        table_names = [item.table_id for item in self.client.list_tables(dataset)]
        if "*" in self.table_id:
            prefix = self.table_id.split("*", 1)[0]
            matched = [name for name in table_names if name.startswith(prefix)]
        else:
            matched = [name for name in table_names if name == self.table_id]
        if not matched:
            raise FileNotFoundError(
                f"Kaynak tablo bulunamadı: {self.source_table}"
            )
        result = {
            "status": "ok",
            "source": self.source_table,
            "output_dataset": self.output_dataset,
            "location": dataset.location,
            "matched_tables": len(matched),
            "identity": "user_id",
            "ltv_type": "observed_historical_ltv",
            "threshold_input": False,
        }
        self._display_status(
            "Bağlantı doğrulandı",
            f"{len(matched)} kaynak tablo bulundu · Bölge: {dataset.location}",
            color="#0f766e",
        )
        return result

    def dry_run(self) -> dict[str, Any]:
        """Estimate both raw GA4 scans before any output table is written."""

        self.validate()
        estimates: list[dict[str, Any]] = []
        total_bytes = 0
        for filename, label in [
            ("01_transaction_base.sql", "Satın alma ve iade tabanı"),
            ("08_monthly_metrics.sql", "Aylık dijital ve e-ticaret metrikleri"),
        ]:
            rendered = self._render_sql(filename)
            marker = "WITH raw AS ("
            if marker not in rendered:
                raise RuntimeError(f"{filename} dry run için ayrıştırılamadı.")
            select_only = rendered[rendered.index(marker) :].rstrip().rstrip(";")
            config = bigquery.QueryJobConfig(
                dry_run=True,
                use_query_cache=False,
                labels={"module": "ga4-ltv-dry-run"},
            )
            job = self.client.query(select_only, job_config=config)
            processed = int(job.total_bytes_processed or 0)
            total_bytes += processed
            estimates.append(
                {
                    "step": label,
                    "bytes": processed,
                    "gb": round(processed / (1024**3), 3),
                }
            )
        result = {
            "status": "ready",
            "source_scan_bytes": total_bytes,
            "source_scan_gb": round(total_bytes / (1024**3), 3),
            "source_scan_tb": round(total_bytes / (1024**4), 4),
            "scans": estimates,
            "writes_performed": False,
            "note": (
                "Toplam, satın alma tabanı ile aylık performans katmanının iki ayrı "
                "ham GA4 taramasını içerir. Sonraki hesaplar çıktı tablolarını okur."
            ),
        }
        self._display_status(
            "Dry run tamamlandı",
            f"Tahmini ham veri taraması: {self._format_bytes(total_bytes)}",
            color="#2563eb",
        )
        return result

    def create_base_table(self) -> dict[str, Any]:
        """Create deduplicated purchase/refund base and data-quality tables."""

        location = self._ensure_output_dataset()
        base_job = self._execute_template("01_transaction_base.sql")
        quality_job = self._execute_template("02_data_quality.sql")
        quality = self._first_row(self._QUALITY_TABLE)
        result = {
            "status": "completed",
            "location": location,
            "base_table": self._table_ref(self._BASE_TABLE),
            "quality_table": self._table_ref(self._QUALITY_TABLE),
            "jobs": [base_job, quality_job],
            "data_quality": quality,
        }
        eligible = int(self._safe_float(quality.get("eligible_purchase_events")))
        purchases = int(self._safe_float(quality.get("purchase_events")))
        coverage = self._safe_float(quality.get("user_id_coverage_rate"))
        self._display_status(
            "Temel tablo hazır",
            f"Analize giren satın alma: {eligible:,} / {purchases:,} · user_id kapsamı: {coverage:.1%}",
            color="#7c3aed",
        )
        return result

    def ltv_analysis(self) -> dict[str, Any]:
        """Build observed LTV outputs, show statistics, insights and charts."""

        self._require_tables(self._BASE_TABLE, self._QUALITY_TABLE)
        jobs = [
            self._execute_template("03_customer_summary.sql"),
            self._execute_template("04_overall_summary.sql"),
            self._execute_template("05_decile_summary.sql"),
            self._execute_template("06_percentile_distribution.sql"),
        ]
        summary = self._first_row(self._SUMMARY_TABLE)
        if not summary or int(self._safe_float(summary.get("customers"))) == 0:
            raise RuntimeError(
                "user_id bulunan satın alma kaydı olmadığı için LTV hesaplanamadı."
            )
        quality = self._first_row(self._QUALITY_TABLE)
        deciles = self._read_table(self._DECILE_TABLE, "ltv_decile")
        percentiles = self._read_table(
            self._PERCENTILE_TABLE, "ltv_percentile"
        )
        basis, currency = self._metric_basis(quality)
        insights = self._build_insights(summary, quality, deciles, basis, currency)
        self._display_ltv_summary(summary, currency, basis)
        figure = self._make_ltv_figure(deciles, percentiles, basis, currency)
        self._show_figure(figure)
        self._display_insights(insights)
        return {
            "status": "completed",
            "metric_basis": basis,
            "currency": currency,
            "summary": summary,
            "insights": insights,
            "tables": {
                "customers": self._table_ref(self._CUSTOMER_TABLE),
                "summary": self._table_ref(self._SUMMARY_TABLE),
                "deciles": self._table_ref(self._DECILE_TABLE),
                "percentiles": self._table_ref(self._PERCENTILE_TABLE),
            },
            "jobs": jobs,
        }

    def monthly_metrics_analysis(self) -> dict[str, Any]:
        """Build monthly ecommerce KPIs and their MoM/YoY comparisons."""

        self._require_tables(self._QUALITY_TABLE)
        jobs = [
            self._execute_template("08_monthly_metrics.sql"),
            self._execute_template("09_monthly_metric_changes.sql"),
        ]
        monthly = self._read_table(self._MONTHLY_TABLE, "month")
        changes = self._read_table(
            self._MONTHLY_CHANGES_TABLE, "month, display_order"
        )
        if monthly.empty:
            raise RuntimeError("Aylık metrik çıktısı üretilemedi.")
        quality = self._first_row(self._QUALITY_TABLE)
        basis, currency = self._metric_basis(quality)
        reporting_month, latest_available_month, is_complete = (
            self._select_reporting_month(monthly)
        )
        latest = monthly.loc[
            monthly["month"] == reporting_month
        ].iloc[0].to_dict()
        latest_changes = changes.loc[
            changes["month"] == reporting_month
        ].copy()
        self._display_monthly_summary(latest, basis, currency)
        if reporting_month != latest_available_month:
            self._display_status(
                "Kısmi ay karşılaştırmadan çıkarıldı",
                f"{str(latest_available_month)[:7]} tabloda tutuldu; kartlar ve karşılaştırmalar için en güncel eksiksiz ay olan {str(reporting_month)[:7]} kullanıldı.",
                color="#b45309",
            )
        elif not is_complete:
            self._display_status(
                "Eksiksiz takvim ayı bulunamadı",
                "Aylık özet mevcut en son dönemi gösteriyor; MoM ve YoY değişimleri eksik kalabilir.",
                color="#b45309",
            )
        figure = self._make_monthly_figure(monthly, basis, currency)
        self._show_figure(figure)
        self._display_monthly_changes(latest_changes, currency)
        return {
            "status": "completed",
            "metric_basis": basis,
            "currency": currency,
            "reporting_month": str(reporting_month),
            "latest_available_month": str(latest_available_month),
            "reporting_month_is_complete": is_complete,
            "latest_metrics": latest,
            "tables": {
                "monthly_metrics": self._table_ref(self._MONTHLY_TABLE),
                "monthly_changes": self._table_ref(self._MONTHLY_CHANGES_TABLE),
            },
            "jobs": jobs,
        }

    def cohort_analysis(self) -> dict[str, Any]:
        """Build a basic first-purchase-month cohort summary."""

        self._require_tables(self._CUSTOMER_TABLE, self._QUALITY_TABLE)
        job = self._execute_template("07_cohort_summary.sql")
        cohorts = self._read_table(self._COHORT_TABLE, "cohort_month")
        if cohorts.empty:
            raise RuntimeError("Kohort çıktısı üretilemedi.")
        quality = self._first_row(self._QUALITY_TABLE)
        basis, currency = self._metric_basis(quality)
        figure = self._make_cohort_figure(cohorts, basis, currency)
        self._show_figure(figure)
        self._display_status(
            "Temel kohort özeti hazır",
            "İlk satın alma ayına göre müşteri sayısı, gözlemlenmiş LTV ve tekrar oranı özetlendi.",
            color="#c2410c",
        )
        return {
            "status": "completed",
            "metric_basis": basis,
            "currency": currency,
            "cohort_rows": int(len(cohorts)),
            "table": self._table_ref(self._COHORT_TABLE),
            "job": job,
        }

    def generate_dashboard(
        self, output_path: str | Path = "ga4_ltv_dashboard.html"
    ) -> str:
        """Create one portable HTML file with embedded charts and tables."""

        self._require_tables(
            self._QUALITY_TABLE,
            self._SUMMARY_TABLE,
            self._DECILE_TABLE,
            self._PERCENTILE_TABLE,
            self._COHORT_TABLE,
            self._MONTHLY_TABLE,
            self._MONTHLY_CHANGES_TABLE,
        )
        quality = self._first_row(self._QUALITY_TABLE)
        summary = self._first_row(self._SUMMARY_TABLE)
        deciles = self._read_table(self._DECILE_TABLE, "ltv_decile")
        percentiles = self._read_table(
            self._PERCENTILE_TABLE, "ltv_percentile"
        )
        cohorts = self._read_table(self._COHORT_TABLE, "cohort_month")
        monthly = self._read_table(self._MONTHLY_TABLE, "month")
        changes = self._read_table(
            self._MONTHLY_CHANGES_TABLE, "month, display_order"
        )
        basis, currency = self._metric_basis(quality)
        insights = self._build_insights(summary, quality, deciles, basis, currency)
        reporting_month, latest_available_month, is_complete = (
            self._select_reporting_month(monthly)
        )
        reporting_month_label = str(reporting_month)[:7]
        latest = monthly.loc[
            monthly["month"] == reporting_month
        ].iloc[0].to_dict()
        latest_changes = changes.loc[
            changes["month"] == reporting_month
        ].copy()
        period_note = (
            f"En yeni mevcut ay {str(latest_available_month)[:7]} kısmi olduğu için kartlarda {reporting_month_label} kullanıldı."
            if reporting_month != latest_available_month
            else (
                f"Kartlar ve değişimler {reporting_month_label} eksiksiz takvim ayını gösterir."
                if is_complete
                else f"Eksiksiz ay bulunamadığı için kartlar {reporting_month_label} kısmi dönemini gösterir."
            )
        )

        ltv_figure = self._make_ltv_figure(
            deciles, percentiles, basis, currency
        )
        monthly_figure = self._make_monthly_figure(monthly, basis, currency)
        cohort_figure = self._make_cohort_figure(cohorts, basis, currency)
        ltv_image = self._figure_data_uri(ltv_figure)
        monthly_image = self._figure_data_uri(monthly_figure)
        cohort_image = self._figure_data_uri(cohort_figure)

        cards = self._dashboard_cards(summary, basis, currency)
        monthly_cards = self._monthly_cards_html(latest, basis, currency)
        insight_items = "".join(
            f"<li>{html.escape(item)}</li>" for item in insights
        )
        decile_rows = self._decile_table_html(deciles, basis, currency)
        monthly_change_rows = self._monthly_change_table_html(
            latest_changes, currency
        )
        quality_rows = self._quality_table_html(quality)
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        document = f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GA4 LTV ve E-ticaret Performans Analizi</title>
  <style>
    :root{{--ink:#172033;--muted:#64748b;--line:#dbe3ef;--bg:#f5f7fb;--card:#fff;--blue:#2563eb;}}
    *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 Inter,Arial,sans-serif}}
    main{{max-width:1180px;margin:auto;padding:36px 22px 64px}} h1{{font-size:32px;margin:0 0 6px}} h2{{font-size:21px;margin:0 0 16px}}
    .sub{{color:var(--muted);margin-bottom:28px}} .grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}}
    .card,.panel{{background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:0 8px 28px rgba(30,41,59,.05)}}
    .card{{padding:18px}} .label{{font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}} .value{{font-size:25px;font-weight:750;margin-top:5px}}
    .panel{{padding:22px;margin-top:18px}} img{{width:100%;height:auto;display:block}} ul{{margin:0;padding-left:20px}} li+li{{margin-top:8px}}
    table{{width:100%;border-collapse:collapse}} th,td{{padding:10px 9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}} th:first-child,td:first-child{{text-align:left}} th{{font-size:12px;color:var(--muted);text-transform:uppercase}}
    .scroll{{overflow-x:auto}} footer{{color:var(--muted);font-size:12px;margin-top:22px}}
    @media(max-width:850px){{.grid{{grid-template-columns:repeat(2,1fr)}}}} @media(max-width:520px){{.grid{{grid-template-columns:1fr}}}}
  </style>
</head>
<body><main>
  <h1>GA4 LTV ve E-ticaret Performans Analizi</h1>
  <div class="sub">user_id bazlı · Eşik kullanılmaz · Gelir temeli: {html.escape(currency)}</div>
  <section class="grid">{cards}</section>
  <section class="panel"><h2>Öne çıkan bulgular</h2><ul>{insight_items}</ul></section>
  <section class="panel"><h2>LTV dağılımı ve gelir yoğunlaşması</h2><img alt="LTV grafikleri" src="{ltv_image}"></section>
  <section class="panel"><h2>{html.escape(reporting_month_label)} e-ticaret göstergeleri</h2><p class="sub">{html.escape(period_note)}</p><div class="grid">{monthly_cards}</div></section>
  <section class="panel"><h2>Aylık performans eğilimleri</h2><img alt="Aylık metrik grafikleri" src="{monthly_image}"></section>
  <section class="panel"><h2>MoM ve YoY karşılaştırması</h2><div class="scroll"><table><thead><tr><th>Metrik</th><th>Değer</th><th>MoM fark</th><th>MoM %</th><th>YoY fark</th><th>YoY %</th></tr></thead><tbody>{monthly_change_rows}</tbody></table></div></section>
  <section class="panel"><h2>Temel ilk satın alma kohortu özeti</h2><img alt="Temel kohort grafikleri" src="{cohort_image}"></section>
  <section class="panel"><h2>LTV dilimleri</h2><div class="scroll"><table><thead><tr><th>Dilim</th><th>Müşteri</th><th>Sipariş</th><th>Ortalama LTV</th><th>Pozitif gelir payı</th><th>Tekrar oranı</th></tr></thead><tbody>{decile_rows}</tbody></table></div></section>
  <section class="panel"><h2>Veri kalitesi</h2><div class="scroll"><table><tbody>{quality_rows}</tbody></table></div></section>
  <footer>Oluşturulma zamanı: {generated}. Bu rapor tahminî LTV değildir. E-ticaret ARPU, net satın alma gelirinin aktif kullanıcılara; ARPPU ise satın alan kullanıcılara bölünmesiyle hesaplanır. MoM ve YoY yalnızca eksiksiz takvim ayları arasında hesaplanır. ROAS, CPA ve CAC için reklam maliyeti kaynağı gerekir ve bu raporda hesaplanmaz.</footer>
</main></body></html>"""

        path = Path(output_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document, encoding="utf-8")
        self._display_status(
            "HTML rapor hazır",
            str(path),
            color="#0f766e",
        )
        return str(path)

    def run_all(self) -> dict[str, Any]:
        """Run the complete flow after showing the source scan estimate."""

        return {
            "dry_run": self.dry_run(),
            "base": self.create_base_table(),
            "ltv": self.ltv_analysis(),
            "monthly_metrics": self.monthly_metrics_analysis(),
            "cohort": self.cohort_analysis(),
            "dashboard": self.generate_dashboard(),
        }

    @staticmethod
    def _safe_float(value: Any) -> float:
        if value is None:
            return 0.0
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return number if number == number else 0.0

    @staticmethod
    def _is_missing(value: Any) -> bool:
        if value is None:
            return True
        try:
            return bool(value != value)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _select_reporting_month(monthly) -> tuple[Any, Any, bool]:
        """Prefer the latest complete calendar month for period comparisons."""

        latest_available = monthly["month"].max()
        if "is_complete_month" not in monthly.columns:
            return latest_available, latest_available, False
        complete = monthly.loc[
            monthly["is_complete_month"].fillna(False).eq(True), "month"
        ]
        if complete.empty:
            return latest_available, latest_available, False
        return complete.max(), latest_available, True

    @staticmethod
    def _format_bytes(value: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = float(value)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:,.2f} {unit}"
            size /= 1024
        return f"{size:,.2f} PB"

    @staticmethod
    def _format_money(value: Any, currency: str) -> str:
        return f"{currency} {LTVAnalyzer._safe_float(value):,.2f}"

    def _format_metric_value(
        self, value: Any, unit: str, currency: str
    ) -> str:
        if self._is_missing(value):
            return "-"
        number = self._safe_float(value)
        if unit == "currency":
            return self._format_money(number, currency)
        if unit == "ratio":
            return f"{number:.1%}"
        if unit == "count":
            return f"{int(round(number)):,}"
        return f"{number:,.2f}"

    def _format_absolute_change(
        self, value: Any, unit: str, currency: str
    ) -> str:
        if self._is_missing(value):
            return "-"
        number = self._safe_float(value)
        if unit == "ratio":
            return f"{number * 100:+.2f} puan"
        if unit == "currency":
            return f"{currency} {number:+,.2f}"
        if unit == "count":
            return f"{int(round(number)):+,}"
        return f"{number:+,.2f}"

    def _metric_basis(self, quality: dict[str, Any]) -> tuple[str, str]:
        local_values = self._safe_float(
            quality.get("purchase_events_with_local_value")
        )
        usd_values = self._safe_float(
            quality.get("purchase_events_with_usd_value")
        )
        currency_count = int(
            self._safe_float(quality.get("distinct_purchase_currencies"))
        )
        currencies = quality.get("purchase_currencies") or []
        if local_values > 0 and currency_count <= 1:
            label = str(currencies[0]) if currencies else "LOCAL"
            return "local", label
        if usd_values > 0:
            return "usd", "USD"
        label = str(currencies[0]) if currencies else "LOCAL"
        return "local", label

    def _build_insights(
        self,
        summary: dict[str, Any],
        quality: dict[str, Any],
        deciles,
        basis: str,
        currency: str,
    ) -> list[str]:
        average = self._safe_float(summary.get(f"average_ltv_{basis}"))
        median = self._safe_float(summary.get(f"median_ltv_{basis}"))
        repeat_rate = self._safe_float(summary.get("repeat_customer_rate"))
        orders_per_customer = self._safe_float(summary.get("orders_per_customer"))
        refund_share = self._safe_float(summary.get(f"refund_share_{basis}"))
        coverage = self._safe_float(quality.get("user_id_coverage_rate"))
        top_share = 0.0
        if not deciles.empty:
            top = deciles.loc[deciles["ltv_decile"] == 1]
            if not top.empty:
                top_share = self._safe_float(
                    top.iloc[0].get(f"positive_revenue_share_{basis}")
                )
        observations = [
            (
                f"Analiz {int(self._safe_float(summary.get('customers'))):,} satın alan "
                f"müşteriyi kapsıyor; müşteri başına ortalama {orders_per_customer:.2f} sipariş var."
            ),
            (
                f"Gözlemlenmiş ortalama LTV {self._format_money(average, currency)}, "
                f"ortanca LTV {self._format_money(median, currency)}."
            ),
            f"Müşterilerin {repeat_rate:.1%} kadarı en az iki sipariş verdi.",
            f"En yüksek LTV'ye sahip ilk %10, pozitif net gelirin {top_share:.1%} kadarını oluşturdu.",
            f"İadelerin brüt gelire oranı {refund_share:.1%}; user_id kapsamı {coverage:.1%}.",
        ]
        if median > 0 and average / median >= 1.5:
            observations.append(
                "Ortalamanın ortancadan belirgin biçimde yüksek olması, gelirin az sayıdaki yüksek değerli müşteride yoğunlaştığını gösteriyor."
            )
        if coverage < 0.70:
            observations.append(
                "user_id kapsamı düşük olduğu için sonuçlar tüm ziyaretçileri değil, kimliği belirlenebilen satın alanları temsil ediyor."
            )
        return observations

    def _display_ltv_summary(
        self, summary: dict[str, Any], currency: str, basis: str
    ) -> None:
        cards = [
            ("Müşteri", f"{int(self._safe_float(summary.get('customers'))):,}"),
            ("Sipariş", f"{int(self._safe_float(summary.get('orders'))):,}"),
            (
                "Ortalama LTV",
                self._format_money(summary.get(f"average_ltv_{basis}"), currency),
            ),
            (
                "Ortanca LTV",
                self._format_money(summary.get(f"median_ltv_{basis}"), currency),
            ),
            (
                "Tekrar satın alan",
                f"{self._safe_float(summary.get('repeat_customer_rate')):.1%}",
            ),
            (
                "Sipariş / müşteri",
                f"{self._safe_float(summary.get('orders_per_customer')):.2f}",
            ),
        ]
        content = "".join(
            f"<div style='padding:14px;border:1px solid #e2e8f0;border-radius:12px;background:#fff'>"
            f"<div style='font-size:11px;color:#64748b;text-transform:uppercase'>{html.escape(label)}</div>"
            f"<div style='font-size:21px;font-weight:750;margin-top:4px'>{html.escape(value)}</div></div>"
            for label, value in cards
        )
        self._display_html(
            "<div style='font-family:Arial,sans-serif;margin:18px 0'>"
            "<div style='font-size:22px;font-weight:750;margin-bottom:12px'>LTV Özeti</div>"
            f"<div style='display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;max-width:980px'>{content}</div></div>"
        )

    def _display_monthly_summary(
        self, latest: dict[str, Any], basis: str, currency: str
    ) -> None:
        month = str(latest.get("month") or "-")[:7]
        cards = [
            ("Ay", month),
            ("Aktif kullanıcı", f"{int(self._safe_float(latest.get('active_users'))):,}"),
            ("Satın alan", f"{int(self._safe_float(latest.get('purchasers'))):,}"),
            ("Sipariş", f"{int(self._safe_float(latest.get('orders'))):,}"),
            ("AOV", self._format_money(latest.get(f"average_order_value_{basis}"), currency)),
            ("E-ticaret ARPU", self._format_money(latest.get(f"ecommerce_arpu_{basis}"), currency)),
            ("E-ticaret ARPPU", self._format_money(latest.get(f"ecommerce_arppu_{basis}"), currency)),
            ("Oturum başına gelir", self._format_money(latest.get(f"revenue_per_session_{basis}"), currency)),
            ("Oturum satın alma oranı", f"{self._safe_float(latest.get('purchase_session_rate')):.1%}"),
            ("Aylık tekrar satın alan", f"{self._safe_float(latest.get('repeat_purchaser_rate')):.1%}"),
        ]
        content = "".join(
            f"<div style='padding:14px;border:1px solid #e2e8f0;border-radius:12px;background:#fff'>"
            f"<div style='font-size:11px;color:#64748b;text-transform:uppercase'>{html.escape(label)}</div>"
            f"<div style='font-size:20px;font-weight:750;margin-top:4px'>{html.escape(value)}</div></div>"
            for label, value in cards
        )
        self._display_html(
            "<div style='font-family:Arial,sans-serif;margin:18px 0'>"
            "<div style='font-size:22px;font-weight:750;margin-bottom:12px'>Aylık E-ticaret ve Dijital Performans</div>"
            f"<div style='display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;max-width:1180px'>{content}</div></div>"
        )

    def _display_monthly_changes(self, frame, currency: str) -> None:
        rows = self._monthly_change_table_html(frame, currency)
        self._display_html(
            "<div style='font-family:Arial,sans-serif;max-width:1180px;margin:16px 0'>"
            "<div style='font-size:20px;font-weight:750;margin-bottom:10px'>Son Ay MoM ve YoY</div>"
            "<div style='overflow-x:auto;border:1px solid #e2e8f0;border-radius:12px;background:#fff'>"
            "<table style='width:100%;border-collapse:collapse'>"
            "<thead><tr><th>Metrik</th><th>Değer</th><th>MoM fark</th><th>MoM %</th><th>YoY fark</th><th>YoY %</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div></div>"
        )

    @staticmethod
    def _make_ltv_figure(deciles, percentiles, basis: str, currency: str):
        import matplotlib.pyplot as plt
        import numpy as np

        frame = deciles.sort_values("ltv_decile").copy()
        curve = percentiles.sort_values("ltv_percentile").copy()
        revenue_column = f"net_revenue_{basis}"
        curve_column = f"cumulative_positive_revenue_share_{basis}"

        fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.8))
        colors = ["#1d4ed8" if int(x) == 1 else "#93c5fd" for x in frame["ltv_decile"]]
        axes[0].bar(
            [f"D{int(x)}" for x in frame["ltv_decile"]],
            frame[revenue_column].astype(float),
            color=colors,
        )
        axes[0].axhline(0, color="#64748b", linewidth=0.8)
        axes[0].set_title("LTV dilimlerine göre net gelir")
        axes[0].set_xlabel("D1 = en yüksek LTV")
        axes[0].set_ylabel(currency)
        axes[0].grid(axis="y", alpha=0.2)

        x = np.r_[0.0, curve["cumulative_customer_share"].astype(float).to_numpy()]
        y = np.r_[0.0, curve[curve_column].fillna(0).astype(float).to_numpy()]
        axes[1].plot(x * 100, y * 100, color="#7c3aed", linewidth=2.5)
        axes[1].plot([0, 100], [0, 100], "--", color="#cbd5e1", linewidth=1)
        axes[1].fill_between(x * 100, y * 100, alpha=0.12, color="#7c3aed")
        axes[1].set_title("Pozitif net gelirin müşteri tabanında yoğunlaşması")
        axes[1].set_xlabel("En yüksek LTV'den başlayarak müşteri payı (%)")
        axes[1].set_ylabel("Kümülatif pozitif net gelir (%)")
        axes[1].set_xlim(0, 100)
        axes[1].set_ylim(0, 105)
        axes[1].grid(alpha=0.2)
        fig.tight_layout()
        return fig

    @staticmethod
    def _make_monthly_figure(monthly, basis: str, currency: str):
        import matplotlib.pyplot as plt
        import pandas as pd

        frame = monthly.copy().sort_values("month")
        if "is_complete_month" in frame.columns:
            complete = frame.loc[
                frame["is_complete_month"].fillna(False).eq(True)
            ].copy()
            if not complete.empty:
                frame = complete
        frame["month"] = pd.to_datetime(frame["month"])
        revenue = f"net_revenue_{basis}"
        arpu = f"ecommerce_arpu_{basis}"
        arppu = f"ecommerce_arppu_{basis}"
        aov = f"average_order_value_{basis}"
        rps = f"revenue_per_session_{basis}"

        fig, axes = plt.subplots(2, 2, figsize=(14, 8.5))
        axes[0, 0].plot(frame["month"], frame[revenue], marker="o", color="#2563eb")
        axes[0, 0].set_title("Aylık net satın alma geliri")
        axes[0, 0].set_ylabel(currency)

        axes[0, 1].plot(frame["month"], frame[arpu], marker="o", label="E-ticaret ARPU", color="#7c3aed")
        axes[0, 1].plot(frame["month"], frame[arppu], marker="o", label="E-ticaret ARPPU", color="#db2777")
        axes[0, 1].set_title("Kullanıcı başına gelir")
        axes[0, 1].set_ylabel(currency)
        axes[0, 1].legend(frameon=False)

        axes[1, 0].plot(frame["month"], frame[aov], marker="o", label="AOV", color="#ea580c")
        axes[1, 0].plot(frame["month"], frame[rps], marker="o", label="Oturum başına gelir", color="#0891b2")
        axes[1, 0].set_title("Sipariş ve oturum değeri")
        axes[1, 0].set_ylabel(currency)
        axes[1, 0].legend(frameon=False)

        axes[1, 1].plot(
            frame["month"],
            frame["purchase_session_rate"].astype(float) * 100,
            marker="o",
            label="Oturum satın alma oranı",
            color="#059669",
        )
        axes[1, 1].plot(
            frame["month"],
            frame["repeat_purchaser_rate"].astype(float) * 100,
            marker="o",
            label="Aylık tekrar satın alan oranı",
            color="#ca8a04",
        )
        axes[1, 1].set_title("Dönüşüm ve tekrar satın alma")
        axes[1, 1].set_ylabel("Oran (%)")
        axes[1, 1].legend(frameon=False)

        for axis in axes.flat:
            axis.grid(alpha=0.2)
            axis.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        return fig

    @staticmethod
    def _make_cohort_figure(cohorts, basis: str, currency: str):
        import matplotlib.pyplot as plt
        import pandas as pd

        frame = cohorts.copy().sort_values("cohort_month")
        frame["cohort_month"] = pd.to_datetime(frame["cohort_month"])
        labels = frame["cohort_month"].dt.strftime("%Y-%m")
        average_ltv = f"average_ltv_{basis}"
        median_ltv = f"median_ltv_{basis}"
        width = max(12.0, min(19.0, len(frame) * 0.65))

        fig, axes = plt.subplots(1, 2, figsize=(width, 5.0))
        axes[0].bar(labels, frame["cohort_size"].astype(float), color="#93c5fd")
        axes[0].set_title("İlk satın alma ayına göre müşteri sayısı")
        axes[0].set_ylabel("Müşteri")

        axes[1].plot(labels, frame[average_ltv], marker="o", label="Ortalama LTV", color="#ea580c")
        axes[1].plot(labels, frame[median_ltv], marker="o", label="Ortanca LTV", color="#7c3aed")
        axes[1].set_title("Kohort bazında gözlemlenmiş LTV")
        axes[1].set_ylabel(currency)
        axes[1].legend(frameon=False)

        for axis in axes:
            axis.grid(axis="y", alpha=0.2)
            axis.tick_params(axis="x", rotation=60)
        fig.tight_layout()
        return fig

    @staticmethod
    def _show_figure(figure) -> None:
        import matplotlib.pyplot as plt

        try:
            from IPython.display import display

            display(figure)
            plt.close(figure)
        except ImportError:
            plt.show()

    @staticmethod
    def _figure_data_uri(figure) -> str:
        import matplotlib.pyplot as plt

        buffer = BytesIO()
        figure.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
        plt.close(figure)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    @staticmethod
    def _display_html(content: str) -> None:
        try:
            from IPython.display import HTML, display

            display(HTML(content))
        except ImportError:
            print(re.sub(r"<[^>]+>", " ", content))

    def _display_status(self, title: str, detail: str, color: str) -> None:
        self._display_html(
            f"<div style='font-family:Arial,sans-serif;border:1px solid #e2e8f0;"
            f"border-left:5px solid {html.escape(color)};border-radius:12px;padding:13px 15px;"
            f"margin:10px 0;max-width:980px;background:#fff'>"
            f"<div style='font-weight:750'>{html.escape(title)}</div>"
            f"<div style='color:#64748b;font-size:13px;margin-top:3px'>{html.escape(detail)}</div></div>"
        )

    def _display_insights(self, insights: list[str]) -> None:
        items = "".join(f"<li>{html.escape(item)}</li>" for item in insights)
        self._display_html(
            "<div style='font-family:Arial,sans-serif;max-width:980px;border:1px solid #e2e8f0;"
            "border-radius:14px;padding:17px 20px;margin:14px 0;background:#f8fafc'>"
            f"<div style='font-size:18px;font-weight:750;margin-bottom:8px'>Analiz notları</div><ul style='margin:0;padding-left:20px'>{items}</ul></div>"
        )

    def _dashboard_cards(
        self, summary: dict[str, Any], basis: str, currency: str
    ) -> str:
        values = [
            ("Müşteri", f"{int(self._safe_float(summary.get('customers'))):,}"),
            ("Sipariş", f"{int(self._safe_float(summary.get('orders'))):,}"),
            (
                "Ortalama LTV",
                self._format_money(summary.get(f"average_ltv_{basis}"), currency),
            ),
            (
                "Ortanca LTV",
                self._format_money(summary.get(f"median_ltv_{basis}"), currency),
            ),
            (
                "Net gelir",
                self._format_money(summary.get(f"net_revenue_{basis}"), currency),
            ),
            (
                "Tekrar oranı",
                f"{self._safe_float(summary.get('repeat_customer_rate')):.1%}",
            ),
            (
                "Sipariş / müşteri",
                f"{self._safe_float(summary.get('orders_per_customer')):.2f}",
            ),
            (
                "İade payı",
                f"{self._safe_float(summary.get(f'refund_share_{basis}')):.1%}",
            ),
        ]
        return "".join(
            f"<div class='card'><div class='label'>{html.escape(label)}</div>"
            f"<div class='value'>{html.escape(value)}</div></div>"
            for label, value in values
        )

    def _monthly_cards_html(
        self, latest: dict[str, Any], basis: str, currency: str
    ) -> str:
        values = [
            ("Aktif kullanıcı", f"{int(self._safe_float(latest.get('active_users'))):,}"),
            ("Satın alan", f"{int(self._safe_float(latest.get('purchasers'))):,}"),
            ("Sipariş", f"{int(self._safe_float(latest.get('orders'))):,}"),
            ("AOV", self._format_money(latest.get(f"average_order_value_{basis}"), currency)),
            ("E-ticaret ARPU", self._format_money(latest.get(f"ecommerce_arpu_{basis}"), currency)),
            ("E-ticaret ARPPU", self._format_money(latest.get(f"ecommerce_arppu_{basis}"), currency)),
            ("Oturum başına gelir", self._format_money(latest.get(f"revenue_per_session_{basis}"), currency)),
            ("Oturum satın alma oranı", f"{self._safe_float(latest.get('purchase_session_rate')):.1%}"),
        ]
        return "".join(
            f"<div class='card'><div class='label'>{html.escape(label)}</div>"
            f"<div class='value'>{html.escape(value)}</div></div>"
            for label, value in values
        )

    def _monthly_change_table_html(self, frame, currency: str) -> str:
        rows: list[str] = []
        for _, row in frame.sort_values("display_order").iterrows():
            unit = str(row.get("metric_unit") or "number")
            value = self._format_metric_value(row.get("metric_value"), unit, currency)
            mom_abs = self._format_absolute_change(row.get("mom_absolute_change"), unit, currency)
            yoy_abs = self._format_absolute_change(row.get("yoy_absolute_change"), unit, currency)
            mom_pct = (
                "-"
                if self._is_missing(row.get("mom_change_pct"))
                else f"{self._safe_float(row.get('mom_change_pct')):+.1%}"
            )
            yoy_pct = (
                "-"
                if self._is_missing(row.get("yoy_change_pct"))
                else f"{self._safe_float(row.get('yoy_change_pct')):+.1%}"
            )
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(row.get('metric_label') or row.get('metric_name')))}</td>"
                f"<td>{html.escape(value)}</td>"
                f"<td>{html.escape(mom_abs)}</td>"
                f"<td>{html.escape(mom_pct)}</td>"
                f"<td>{html.escape(yoy_abs)}</td>"
                f"<td>{html.escape(yoy_pct)}</td>"
                "</tr>"
            )
        return "".join(rows)

    def _decile_table_html(self, frame, basis: str, currency: str) -> str:
        rows: list[str] = []
        for _, row in frame.sort_values("ltv_decile").iterrows():
            rows.append(
                "<tr>"
                f"<td>D{int(row['ltv_decile'])}</td>"
                f"<td>{int(self._safe_float(row['customers'])):,}</td>"
                f"<td>{int(self._safe_float(row['orders'])):,}</td>"
                f"<td>{html.escape(self._format_money(row[f'average_ltv_{basis}'], currency))}</td>"
                f"<td>{self._safe_float(row[f'positive_revenue_share_{basis}']):.1%}</td>"
                f"<td>{self._safe_float(row['repeat_customer_rate']):.1%}</td>"
                "</tr>"
            )
        return "".join(rows)

    def _quality_table_html(self, quality: dict[str, Any]) -> str:
        rows = [
            ("Veri başlangıcı", str(quality.get("data_start_date") or "-")),
            ("Veri bitişi", str(quality.get("data_end_date") or "-")),
            ("Satın alma olayı", f"{int(self._safe_float(quality.get('purchase_events'))):,}"),
            ("İade olayı", f"{int(self._safe_float(quality.get('refund_events'))):,}"),
            ("user_id kapsamı", f"{self._safe_float(quality.get('user_id_coverage_rate')):.1%}"),
            ("transaction_id kapsamı", f"{self._safe_float(quality.get('transaction_id_coverage_rate')):.1%}"),
            ("Gelir alanı kapsamı", f"{self._safe_float(quality.get('revenue_coverage_rate')):.1%}"),
        ]
        return "".join(
            f"<tr><td>{html.escape(label)}</td><td>{html.escape(value)}</td></tr>"
            for label, value in rows
        )
