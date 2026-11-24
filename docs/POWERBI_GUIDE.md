# Power BI guide

`python -m retailpulse.cli run-all` writes star-schema CSVs (PII columns removed) to `artifacts/powerbi/`.
Power BI Desktop runs on **Windows** (a laptop or college PC); on a phone, use the Power BI web service or do this step later.
The DAX below was **not run in Power BI** during authoring; it follows the standard patterns, so verify each measure against `RESULTS.md`.

## 1. Load
Get Data -> Text/CSV: `dim_customer`, `dim_product`, `dim_date`, `fact_orders`, `fact_order_items`, `returns`.
In Power Query set `dim_date[full_date]` to **Date**. Mark `dim_date` as the date table.

## 2. Relationships (all many-to-one, single direction)
| From (many) | To (one) |
|---|---|
| `fact_order_items[order_id]` | `fact_orders[order_id]` |
| `fact_order_items[product_key]` | `dim_product[product_key]` |
| `fact_orders[customer_key]` | `dim_customer[customer_key]` |
| `fact_orders[date_key]` | `dim_date[date_key]` |

## 3. Measures
```dax
Net Revenue = CALCULATE ( SUM ( fact_order_items[revenue] ), fact_orders[is_returned] = 0 )
Net Profit  = CALCULATE ( SUM ( fact_order_items[revenue] ) - SUM ( fact_order_items[cost] ), fact_orders[is_returned] = 0 )
Margin %    = DIVIDE ( [Net Profit], [Net Revenue] )
Orders      = DISTINCTCOUNT ( fact_orders[order_id] )
Net Orders  = CALCULATE ( [Orders], fact_orders[is_returned] = 0 )
AOV         = DIVIDE ( [Net Revenue], [Net Orders] )
Return Rate = DIVIDE ( CALCULATE ( [Orders], fact_orders[is_returned] = 1 ), [Orders] )
Customers   = DISTINCTCOUNT ( fact_orders[customer_key] )
Revenue LM  = CALCULATE ( [Net Revenue], DATEADD ( dim_date[full_date], -1, MONTH ) )
Revenue MoM % = DIVIDE ( [Net Revenue] - [Revenue LM], [Revenue LM] )
```
Check: `Net Revenue` over all dates should equal the KPI in `artifacts/reports/RESULTS.md`.

## 4. Pages
1. **Executive:** KPI cards (Net Revenue, Margin %, Orders, AOV, Return Rate), monthly revenue line, category bar, city bar, slicers for year / channel.
2. **Customers:** import `artifacts/rfm.csv` (segment counts, avg monetary); import `churn_scores.csv` (top value-at-risk table).
3. **Forecast:** import `forecast.csv`; line chart of `forecast`, `lower`, `upper` by `date`.

## 5. Design rules that make dashboards look professional
- One chart = one question; title states the question or the finding.
- Single series -> one colour; do not use a rainbow. No dual axes.
- Label the important values directly; keep gridlines faint.
- Put filters in one row at the top; test with a very small and very large selection.
- Add a footnote: "Synthetic data, seed 42".
