-- RetailPulse: 15 business questions answered in SQL (SQLite dialect).
-- Convention: "net revenue" excludes returned orders (is_returned = 0).
-- Each block starts with "-- name: <id>" so Python can load it by name.

-- name: monthly_revenue
-- Skill: GROUP BY, aggregates, printf
SELECT printf('%04d-%02d', year, month) AS month,
       ROUND(SUM(revenue), 2)           AS net_revenue,
       COUNT(DISTINCT order_id)         AS orders,
       ROUND(SUM(profit), 2)            AS profit
FROM vw_sales
WHERE is_returned = 0
GROUP BY year, month
ORDER BY year, month;

-- name: category_performance
-- Skill: window over aggregate (share of total)
SELECT category,
       ROUND(SUM(revenue), 2)                                     AS net_revenue,
       SUM(quantity)                                              AS units,
       ROUND(100.0 * SUM(profit) / SUM(revenue), 1)               AS margin_pct,
       ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 1) AS revenue_share_pct
FROM vw_sales
WHERE is_returned = 0
GROUP BY category
ORDER BY net_revenue DESC;

-- name: city_revenue_rank
-- Skill: RANK() window function
SELECT city,
       ROUND(SUM(revenue), 2) AS net_revenue,
       RANK() OVER (ORDER BY SUM(revenue) DESC) AS revenue_rank
FROM vw_sales
WHERE is_returned = 0
GROUP BY city
ORDER BY revenue_rank;

-- name: top_products
-- Skill: ORDER BY + LIMIT
SELECT product_name, category,
       ROUND(SUM(revenue), 2) AS net_revenue,
       SUM(quantity)          AS units
FROM vw_sales
WHERE is_returned = 0
GROUP BY product_key
ORDER BY net_revenue DESC
LIMIT 10;

-- name: running_total_revenue
-- Skill: CTE + cumulative SUM() OVER
WITH m AS (
    SELECT year, month, SUM(revenue) AS rev
    FROM vw_sales WHERE is_returned = 0
    GROUP BY year, month
)
SELECT printf('%04d-%02d', year, month)               AS month,
       ROUND(rev, 2)                                  AS net_revenue,
       ROUND(SUM(rev) OVER (ORDER BY year, month), 2) AS cumulative_revenue
FROM m
ORDER BY year, month;

-- name: mom_growth
-- Skill: LAG() for period-over-period change
WITH m AS (
    SELECT year, month, SUM(revenue) AS rev
    FROM vw_sales WHERE is_returned = 0
    GROUP BY year, month
)
SELECT printf('%04d-%02d', year, month) AS month,
       ROUND(rev, 2) AS net_revenue,
       ROUND(100.0 * (rev - LAG(rev) OVER (ORDER BY year, month))
             / LAG(rev) OVER (ORDER BY year, month), 1) AS mom_growth_pct
FROM m
ORDER BY year, month;

-- name: channel_payment_mix
-- Skill: PARTITION BY (percent within group)
WITH mix AS (
    SELECT channel, payment_method, COUNT(*) AS orders
    FROM fact_orders
    GROUP BY channel, payment_method
)
SELECT channel, payment_method, orders,
       ROUND(100.0 * orders / SUM(orders) OVER (PARTITION BY channel), 1) AS pct_within_channel
FROM mix
ORDER BY channel, orders DESC;

-- name: return_rate_by_category
-- Skill: conditional aggregation
SELECT category,
       COUNT(*)            AS items_sold,
       SUM(is_returned)    AS items_returned,
       ROUND(100.0 * SUM(is_returned) / COUNT(*), 2) AS return_rate_pct
FROM vw_sales
GROUP BY category
ORDER BY return_rate_pct DESC;

-- name: weekend_vs_weekday
-- Skill: CTE + CASE
WITH daily AS (
    SELECT order_date, is_weekend, SUM(revenue) AS rev
    FROM vw_sales WHERE is_returned = 0
    GROUP BY order_date, is_weekend
)
SELECT CASE is_weekend WHEN 1 THEN 'Weekend' ELSE 'Weekday' END AS day_type,
       ROUND(AVG(rev), 2) AS avg_daily_revenue,
       COUNT(*)           AS days
FROM daily
GROUP BY is_weekend;

-- name: festive_uplift
-- Skill: seasonality comparison
WITH daily AS (
    SELECT order_date, is_festive_season AS festive, SUM(revenue) AS rev
    FROM vw_sales WHERE is_returned = 0
    GROUP BY order_date, is_festive_season
)
SELECT CASE festive WHEN 1 THEN 'Festive (Oct-Nov)' ELSE 'Regular' END AS period,
       ROUND(AVG(rev), 2) AS avg_daily_revenue,
       COUNT(*)           AS days
FROM daily
GROUP BY festive;

-- name: customer_ltv_top
-- Skill: customer value ranking (no PII columns)
SELECT customer_key, city,
       COUNT(DISTINCT order_id) AS orders,
       ROUND(SUM(revenue), 2)   AS net_revenue
FROM vw_sales
WHERE is_returned = 0
GROUP BY customer_key
ORDER BY net_revenue DESC
LIMIT 20;

-- name: repeat_purchase_rate
-- Skill: CTE + boolean aggregation
WITH per_customer AS (
    SELECT customer_key, COUNT(*) AS orders FROM fact_orders GROUP BY customer_key
)
SELECT COUNT(*)                                             AS customers,
       SUM(orders >= 2)                                     AS repeat_customers,
       ROUND(100.0 * SUM(orders >= 2) / COUNT(*), 1)        AS repeat_rate_pct,
       ROUND(AVG(orders), 2)                                AS avg_orders_per_customer
FROM per_customer;

-- name: cohort_sizes
-- Skill: first-event cohorting
WITH first_order AS (
    SELECT o.customer_key, MIN(d.full_date) AS first_date
    FROM fact_orders o JOIN dim_date d USING (date_key)
    GROUP BY o.customer_key
)
SELECT substr(first_date, 1, 7) AS cohort_month, COUNT(*) AS new_customers
FROM first_order
GROUP BY cohort_month
ORDER BY cohort_month;

-- name: pareto_products
-- Skill: ABC / Pareto analysis with cumulative windows
WITH p AS (
    SELECT product_key, SUM(revenue) AS rev
    FROM vw_sales WHERE is_returned = 0
    GROUP BY product_key
),
ranked AS (
    SELECT rev,
           SUM(rev) OVER (ORDER BY rev DESC) AS cum_rev,
           SUM(rev) OVER ()                  AS total
    FROM p
)
SELECT CASE WHEN cum_rev <= 0.80 * total THEN 'A (top 80% of revenue)'
            WHEN cum_rev <= 0.95 * total THEN 'B (next 15%)'
            ELSE 'C (last 5%)' END AS abc_class,
       COUNT(*)            AS products,
       ROUND(SUM(rev), 2)  AS net_revenue
FROM ranked
GROUP BY abc_class
ORDER BY abc_class;

-- name: discount_effectiveness
-- Skill: does discounting lift volume or just erode margin?
SELECT discount_pct,
       COUNT(*)                                   AS line_items,
       ROUND(AVG(quantity), 2)                    AS avg_units_per_line,
       ROUND(100.0 * SUM(profit) / SUM(revenue), 1) AS margin_pct,
       ROUND(SUM(revenue), 2)                     AS net_revenue
FROM vw_sales
WHERE is_returned = 0
GROUP BY discount_pct
ORDER BY discount_pct;
