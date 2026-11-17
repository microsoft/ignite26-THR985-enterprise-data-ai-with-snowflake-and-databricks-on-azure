-- Step 30 · Silver -> gold: the data products other teams, agents and Databricks consume ('<product>/gold/<table>').
-- Region is denormalized onto the facts so one row access policy covers sales, notes and loyalty (step 40).
-- Re-running this file recreates the gold tables and drops their policies - re-run 40 onwards afterwards.

USE ROLE CORE_OWNER;
USE WAREHOUSE {{WAREHOUSE}};

-- Core: conformed dimensions shared by every product ------------------------------------------------------------------
CREATE OR REPLACE ICEBERG TABLE CORE.GOLD.DIM_DATE (
  date_key INT, calendar_date DATE, day_of_week INT, day_name STRING, week_start_date DATE, iso_year INT,
  iso_week INT, month_num INT, month_name STRING, quarter_num INT, year_num INT, is_weekend BOOLEAN, holiday_name STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_CORE' BASE_LOCATION = 'gold/dim_date'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
  COMMENT = 'Calendar. Weeks run Monday to Sunday; week_start_date is the Monday.'
AS SELECT * FROM CORE.SILVER.DIM_DATE;

CREATE OR REPLACE ICEBERG TABLE CORE.GOLD.DIM_STORE (
  store_id STRING, store_name STRING, store_format STRING, city STRING, state STRING, region STRING, dc_id STRING,
  sqft INT, open_date DATE)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_CORE' BASE_LOCATION = 'gold/dim_store'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
  COMMENT = '48 stores in 4 regions (West, East, Central, South). Formats: Superstore, Neighborhood, Express.'
AS SELECT * FROM CORE.SILVER.DIM_STORE;

CREATE OR REPLACE ICEBERG TABLE CORE.GOLD.DIM_DC (
  dc_id STRING, dc_name STRING, city STRING, state STRING, region STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_CORE' BASE_LOCATION = 'gold/dim_dc'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
  COMMENT = 'Distribution centers; each region is served by one DC.'
AS SELECT * FROM CORE.SILVER.DIM_DC;

CREATE OR REPLACE ICEBERG TABLE CORE.GOLD.DIM_SUPPLIER (
  supplier_id STRING, supplier_name STRING, category STRING, hq_city STRING, hq_state STRING, avg_lead_time_days INT)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_CORE' BASE_LOCATION = 'gold/dim_supplier'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
  COMMENT = 'Suppliers. Northwind Traders (SUP01) supplies all beverages.'
AS SELECT * FROM CORE.SILVER.DIM_SUPPLIER;

CREATE OR REPLACE ICEBERG TABLE CORE.GOLD.DIM_PRODUCT (
  sku STRING, product_name STRING, brand STRING, category STRING, subcategory STRING, supplier_id STRING,
  is_private_label BOOLEAN, unit_price DECIMAL(10,2), unit_cost DECIMAL(10,2), case_pack INT, status STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_CORE' BASE_LOCATION = 'gold/dim_product'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
  COMMENT = '200 SKUs in 8 categories, with list price and unit cost.'
AS SELECT * FROM CORE.SILVER.DIM_PRODUCT;

-- Other product owners join to core; governance applies policies. Readers are granted in step 50.
GRANT USAGE ON DATABASE CORE TO ROLE COMMERCIAL_OWNER;
GRANT USAGE ON DATABASE CORE TO ROLE LOYALTY_OWNER;
GRANT USAGE ON DATABASE CORE TO ROLE GOVERNANCE_ADMIN;
GRANT USAGE ON SCHEMA CORE.GOLD TO ROLE COMMERCIAL_OWNER;
GRANT USAGE ON SCHEMA CORE.GOLD TO ROLE LOYALTY_OWNER;
GRANT USAGE ON SCHEMA CORE.GOLD TO ROLE GOVERNANCE_ADMIN;
GRANT SELECT ON ALL ICEBERG TABLES IN SCHEMA CORE.GOLD TO ROLE COMMERCIAL_OWNER;
GRANT SELECT ON ALL ICEBERG TABLES IN SCHEMA CORE.GOLD TO ROLE LOYALTY_OWNER;

-- Commercial -----------------------------------------------------------------------------------------------------------
USE ROLE COMMERCIAL_OWNER;
CREATE OR REPLACE ICEBERG TABLE COMMERCIAL.GOLD.FACT_SALES_DAILY (
  sales_date DATE, week_start_date DATE, store_id STRING, region STRING, sku STRING, units_sold INT,
  gross_sales DECIMAL(12,2), discount_amount DECIMAL(12,2), net_sales DECIMAL(12,2), cogs DECIMAL(12,2),
  gross_margin DECIMAL(12,2), promo_id STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_COMMERCIAL' BASE_LOCATION = 'gold/fact_sales_daily'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
  COMMENT = 'Daily sales by store and SKU (rows only where units were sold). promo_id is set when the sale was on promotion.'
AS SELECT s.sales_date, d.week_start_date, s.store_id, st.region, s.sku, s.units_sold, s.gross_sales,
          s.discount_amount, s.net_sales, s.cogs, s.gross_margin, s.promo_id
   FROM COMMERCIAL.SILVER.FACT_SALES_DAILY s
   JOIN CORE.GOLD.DIM_STORE st ON st.store_id = s.store_id
   JOIN CORE.GOLD.DIM_DATE d ON d.calendar_date = s.sales_date;

CREATE OR REPLACE ICEBERG TABLE COMMERCIAL.GOLD.DIM_PROMOTION (
  promo_id STRING, promo_name STRING, promo_type STRING, discount_pct DECIMAL(5,2), start_date DATE, end_date DATE,
  region_scope STRING, category STRING, subcategory STRING, expected_lift_pct INT, funding_type STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_COMMERCIAL' BASE_LOCATION = 'gold/dim_promotion'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
  COMMENT = 'Promotions. region_scope is a region name or All. Holiday Kickoff = {{PROMO_ID}}.'
AS SELECT * FROM COMMERCIAL.SILVER.DIM_PROMOTION;

CREATE OR REPLACE ICEBERG TABLE COMMERCIAL.GOLD.BRIDGE_PROMOTION_SKU (promo_id STRING, sku STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_COMMERCIAL' BASE_LOCATION = 'gold/bridge_promotion_sku'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
  COMMENT = 'Which SKUs each promotion covers.'
AS SELECT * FROM COMMERCIAL.SILVER.BRIDGE_PROMOTION_SKU;

-- Change tracking feeds the per-region Cortex Search services (step 75).
CREATE OR REPLACE ICEBERG TABLE COMMERCIAL.GOLD.FIELD_NOTES (
  note_id STRING, note_ts TIMESTAMP_NTZ(6), note_date DATE, region STRING, store_id STRING, author_role STRING,
  topic STRING, promo_id STRING, note_text STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_COMMERCIAL' BASE_LOCATION = 'gold/field_notes'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
  CHANGE_TRACKING = TRUE
  COMMENT = 'Free-text notes from stores, DCs and category managers. region = All for company-wide notes.'
AS SELECT * FROM COMMERCIAL.SILVER.FIELD_NOTES;

GRANT USAGE ON DATABASE COMMERCIAL TO ROLE GOVERNANCE_ADMIN;
GRANT USAGE ON SCHEMA COMMERCIAL.GOLD TO ROLE GOVERNANCE_ADMIN;

-- Loyalty --------------------------------------------------------------------------------------------------------------
USE ROLE LOYALTY_OWNER;
CREATE OR REPLACE ICEBERG TABLE LOYALTY.GOLD.DIM_MEMBER (
  member_id STRING, first_name STRING, last_name STRING, email STRING, phone STRING, birth_year INT,
  loyalty_tier STRING, join_date DATE, home_store_id STRING, home_region STRING, marketing_opt_in BOOLEAN)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_LOYALTY' BASE_LOCATION = 'gold/dim_member'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
  COMMENT = 'Loyalty members (PII: names, email, phone, birth year are masked). Tiers: Gold, Silver, Bronze.'
AS SELECT * FROM LOYALTY.SILVER.DIM_MEMBER;

CREATE OR REPLACE ICEBERG TABLE LOYALTY.GOLD.FACT_MEMBER_WEEKLY (
  week_start_date DATE, member_id STRING, home_store_id STRING, home_region STRING, loyalty_tier STRING, visits INT,
  net_sales DECIMAL(12,2), beverage_sales DECIMAL(12,2), promo_redemptions INT)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_LOYALTY' BASE_LOCATION = 'gold/fact_member_weekly'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
  COMMENT = 'Weekly activity per loyalty member (Monday week start), with the member''s home region and current tier.'
AS SELECT f.week_start_date, f.member_id, f.home_store_id, m.home_region, m.loyalty_tier, f.visits, f.net_sales,
          f.beverage_sales, f.promo_redemptions
   FROM LOYALTY.SILVER.FACT_MEMBER_WEEKLY f
   JOIN LOYALTY.SILVER.DIM_MEMBER m ON m.member_id = f.member_id;

GRANT USAGE ON DATABASE LOYALTY TO ROLE GOVERNANCE_ADMIN;
GRANT USAGE ON SCHEMA LOYALTY.GOLD TO ROLE GOVERNANCE_ADMIN;

-- Where did the files land? (metadata location per gold table - the path Databricks reads)
USE ROLE COMMERCIAL_OWNER;
SELECT SYSTEM$GET_ICEBERG_TABLE_INFORMATION('COMMERCIAL.GOLD.FACT_SALES_DAILY') AS sales_metadata;
USE ROLE CORE_OWNER;
SELECT SYSTEM$GET_ICEBERG_TABLE_INFORMATION('CORE.GOLD.DIM_STORE') AS store_metadata;
