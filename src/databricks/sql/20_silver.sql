-- Step 20 · Bronze -> silver: typed, de-duplicated Unity Catalog managed tables (Delta). 'date' becomes snapshot_date
-- so no engine trips over the keyword. Tables are dropped and recreated, so re-running is safe.

DROP TABLE IF EXISTS demand_forecast.silver.fact_demand_forecast_weekly;
CREATE TABLE demand_forecast.silver.fact_demand_forecast_weekly
  COMMENT 'Silver: one row per forecast week, store and SKU (latest generated_at wins)'
AS SELECT CAST(forecast_week_start AS DATE) AS forecast_week_start, store_id, sku,
          CAST(forecast_units AS DOUBLE) AS forecast_units, CAST(forecast_p10 AS DOUBLE) AS forecast_p10,
          CAST(forecast_p90 AS DOUBLE) AS forecast_p90, CAST(promo_flag AS BOOLEAN) AS promo_flag, model_name,
          model_version, CAST(generated_at AS TIMESTAMP_NTZ) AS generated_at
   FROM read_files('/Volumes/demand_forecast/bronze/landing/fact_demand_forecast_weekly.parquet', format => 'parquet')
   QUALIFY ROW_NUMBER() OVER (PARTITION BY forecast_week_start, store_id, sku ORDER BY generated_at DESC) = 1;

DROP TABLE IF EXISTS supply_chain.silver.fact_inventory_daily;
CREATE TABLE supply_chain.silver.fact_inventory_daily
  COMMENT 'Silver: end-of-day inventory snapshot per store and SKU'
AS SELECT CAST(`date` AS DATE) AS snapshot_date, store_id, sku, CAST(on_hand_units AS INT) AS on_hand_units,
          CAST(on_order_units AS INT) AS on_order_units, CAST(received_units AS INT) AS received_units,
          CAST(stockout_flag AS BOOLEAN) AS stockout_flag, CAST(days_of_supply AS DOUBLE) AS days_of_supply
   FROM read_files('/Volumes/supply_chain/bronze/landing/fact_inventory_daily.parquet', format => 'parquet')
   QUALIFY ROW_NUMBER() OVER (PARTITION BY `date`, store_id, sku ORDER BY on_hand_units) = 1;

DROP TABLE IF EXISTS supply_chain.silver.fact_supplier_po;
CREATE TABLE supply_chain.silver.fact_supplier_po
  COMMENT 'Silver: supplier purchase-order lines to the distribution centers'
AS SELECT po_number, CAST(po_line AS INT) AS po_line, supplier_id, dc_id, sku, CAST(order_date AS DATE) AS order_date,
          CAST(promised_date AS DATE) AS promised_date, CAST(delivered_date AS DATE) AS delivered_date,
          CAST(ordered_qty AS INT) AS ordered_qty, CAST(delivered_qty AS INT) AS delivered_qty,
          CAST(delay_days AS INT) AS delay_days, CAST(fill_rate AS DECIMAL(5,3)) AS fill_rate, status, reason_code
   FROM read_files('/Volumes/supply_chain/bronze/landing/fact_supplier_po.parquet', format => 'parquet')
   QUALIFY ROW_NUMBER() OVER (PARTITION BY po_number, po_line ORDER BY delivered_date DESC NULLS LAST) = 1;

SELECT 'demand_forecast.silver.fact_demand_forecast_weekly' AS table_name, COUNT(*) AS row_count
FROM demand_forecast.silver.fact_demand_forecast_weekly
UNION ALL SELECT 'supply_chain.silver.fact_inventory_daily', COUNT(*) FROM supply_chain.silver.fact_inventory_daily
UNION ALL SELECT 'supply_chain.silver.fact_supplier_po', COUNT(*) FROM supply_chain.silver.fact_supplier_po;
