-- Step 30 · Silver -> gold, joining Snowflake's core data product through catalog federation (sf_core: Databricks
-- compute reads Snowflake's Iceberg files directly). Region is denormalized so one row filter covers each table.
-- Snowflake's sales stay in Snowflake: governed views read them live (sf_commercial), filtered by the caller's Entra
-- group, because row filters can't be set on foreign tables (spike S1) and Snowflake's row access policies don't
-- travel with catalog federation (war story B: metadata moves, policy doesn't).
-- Re-running drops and recreates the tables - re-run 40 afterwards to re-attach the row filters.

-- Row filter: Entra region groups see their region; HQ analysts and data admins see every region.
CREATE OR REPLACE FUNCTION demand_forecast.gold.rf_region(region STRING)
  RETURNS BOOLEAN
  COMMENT 'Row filter by Entra group (automatic identity management): region groups see their region; HQ and admins see all'
  RETURN is_account_group_member('{{GROUP_ADMINS}}') OR is_account_group_member('{{GROUP_HQ}}') OR is_member('admins')
      OR (region = 'West' AND is_account_group_member('{{GROUP_WEST}}'))
      OR (region = 'East' AND is_account_group_member('{{GROUP_EAST}}'))
      OR (region = 'Central' AND is_account_group_member('{{GROUP_CENTRAL}}'))
      OR (region = 'South' AND is_account_group_member('{{GROUP_SOUTH}}'));

CREATE OR REPLACE FUNCTION supply_chain.gold.rf_region(region STRING)
  RETURNS BOOLEAN
  COMMENT 'Row filter by Entra group (automatic identity management): region groups see their region; HQ and admins see all'
  RETURN is_account_group_member('{{GROUP_ADMINS}}') OR is_account_group_member('{{GROUP_HQ}}') OR is_member('admins')
      OR (region = 'West' AND is_account_group_member('{{GROUP_WEST}}'))
      OR (region = 'East' AND is_account_group_member('{{GROUP_EAST}}'))
      OR (region = 'Central' AND is_account_group_member('{{GROUP_CENTRAL}}'))
      OR (region = 'South' AND is_account_group_member('{{GROUP_SOUTH}}'));

-- Demand forecast ------------------------------------------------------------------------------------------------------
DROP TABLE IF EXISTS demand_forecast.gold.forecast_weekly;
CREATE TABLE demand_forecast.gold.forecast_weekly
  COMMENT 'Weekly unconstrained demand forecast by store and SKU, including two future weeks. Store and product attributes come from the core data product (Snowflake) via catalog federation.'
AS SELECT f.forecast_week_start AS week_start_date, f.store_id, s.store_name, s.store_format, s.region, s.dc_id,
          f.sku, p.product_name, p.brand, p.category, p.subcategory, p.supplier_id,
          f.forecast_units, f.forecast_p10, f.forecast_p90, f.promo_flag, f.model_name, f.model_version, f.generated_at
   FROM demand_forecast.silver.fact_demand_forecast_weekly f
   JOIN sf_core.gold.dim_store s ON s.store_id = f.store_id
   JOIN sf_core.gold.dim_product p ON p.sku = f.sku;

CREATE OR REPLACE VIEW demand_forecast.gold.v_promotion_skus
  COMMENT 'Promotions and the SKUs they cover - read live from Snowflake (commercial data product) via catalog federation. Holiday Kickoff = {{PROMO_ID}}.'
AS SELECT p.promo_id, p.promo_name, p.promo_type, p.discount_pct, p.start_date, p.end_date, p.region_scope,
          p.expected_lift_pct, b.sku
   FROM sf_commercial.gold.dim_promotion p
   JOIN sf_commercial.gold.bridge_promotion_sku b ON b.promo_id = p.promo_id;

CREATE OR REPLACE VIEW demand_forecast.gold.v_sales_weekly
  COMMENT 'Governed view: weekly actual sales by store and SKU, read live from Snowflake (commercial) via catalog federation and filtered to the caller''s regions.'
AS SELECT s.week_start_date, s.store_id, s.region, s.sku, SUM(s.units_sold) AS units_sold,
          SUM(s.net_sales) AS net_sales, SUM(CASE WHEN s.promo_id IS NOT NULL THEN s.units_sold ELSE 0 END) AS promo_units
   FROM sf_commercial.gold.fact_sales_daily s
   WHERE demand_forecast.gold.rf_region(s.region)
   GROUP BY s.week_start_date, s.store_id, s.region, s.sku;

CREATE OR REPLACE VIEW demand_forecast.gold.v_forecast_vs_actual
  COMMENT 'Forecast vs actual units by week, store and SKU for weeks that have actuals (through {{DEMO_WEEK_START}}). variance % = (SUM(actual_units) / SUM(forecast_units) - 1) * 100. Filtered to the caller''s regions.'
AS SELECT f.week_start_date, f.store_id, f.store_name, f.store_format, f.region, f.sku, f.product_name, f.brand,
          f.category, f.subcategory, f.promo_flag, f.forecast_units, f.forecast_p10, f.forecast_p90,
          COALESCE(a.units_sold, 0) AS actual_units, COALESCE(a.net_sales, 0) AS actual_net_sales,
          COALESCE(a.promo_units, 0) AS actual_promo_units
   FROM demand_forecast.gold.forecast_weekly f
   LEFT JOIN demand_forecast.gold.v_sales_weekly a
     ON a.week_start_date = f.week_start_date AND a.store_id = f.store_id AND a.sku = f.sku
   WHERE f.week_start_date <= DATE'{{DEMO_WEEK_START}}' AND demand_forecast.gold.rf_region(f.region);

-- Supply chain ---------------------------------------------------------------------------------------------------------
DROP TABLE IF EXISTS supply_chain.gold.inventory_daily;
CREATE TABLE supply_chain.gold.inventory_daily
  COMMENT 'End-of-day inventory by store and SKU. stockout_flag = no units on hand at close. Store, product and supplier attributes come from the core data product (Snowflake) via catalog federation.'
AS SELECT i.snapshot_date, d.week_start_date, i.store_id, s.store_name, s.store_format, s.region, s.dc_id,
          i.sku, p.product_name, p.brand, p.category, p.subcategory, p.supplier_id, sup.supplier_name,
          i.on_hand_units, i.on_order_units, i.received_units, i.stockout_flag, i.days_of_supply
   FROM supply_chain.silver.fact_inventory_daily i
   JOIN sf_core.gold.dim_store s ON s.store_id = i.store_id
   JOIN sf_core.gold.dim_product p ON p.sku = i.sku
   JOIN sf_core.gold.dim_supplier sup ON sup.supplier_id = p.supplier_id
   JOIN sf_core.gold.dim_date d ON d.calendar_date = i.snapshot_date;

DROP TABLE IF EXISTS supply_chain.gold.supplier_po;
CREATE TABLE supply_chain.gold.supplier_po
  COMMENT 'Supplier purchase-order lines to the distribution centers. region = the DC''s region. delay_days = delivered_date - promised_date; fill_rate = delivered_qty / ordered_qty.'
AS SELECT po.po_number, po.po_line, po.supplier_id, sup.supplier_name, po.dc_id, dc.dc_name, dc.region,
          po.sku, p.product_name, p.category, po.order_date, po.promised_date, po.delivered_date, po.ordered_qty,
          po.delivered_qty, po.delay_days, po.fill_rate, po.status, po.reason_code
   FROM supply_chain.silver.fact_supplier_po po
   JOIN sf_core.gold.dim_supplier sup ON sup.supplier_id = po.supplier_id
   JOIN sf_core.gold.dim_dc dc ON dc.dc_id = po.dc_id
   JOIN sf_core.gold.dim_product p ON p.sku = po.sku;

CREATE OR REPLACE VIEW supply_chain.gold.v_promotion_skus
  COMMENT 'Promotions and the SKUs they cover - read live from Snowflake (commercial data product) via catalog federation. Holiday Kickoff = {{PROMO_ID}}.'
AS SELECT p.promo_id, p.promo_name, p.promo_type, p.discount_pct, p.start_date, p.end_date, p.region_scope,
          p.expected_lift_pct, b.sku
   FROM sf_commercial.gold.dim_promotion p
   JOIN sf_commercial.gold.bridge_promotion_sku b ON b.promo_id = p.promo_id;

SELECT 'demand_forecast.gold.forecast_weekly' AS table_name, COUNT(*) AS row_count FROM demand_forecast.gold.forecast_weekly
UNION ALL SELECT 'supply_chain.gold.inventory_daily', COUNT(*) FROM supply_chain.gold.inventory_daily
UNION ALL SELECT 'supply_chain.gold.supplier_po', COUNT(*) FROM supply_chain.gold.supplier_po
UNION ALL SELECT 'demand_forecast.gold.v_promotion_skus', COUNT(*) FROM demand_forecast.gold.v_promotion_skus;
