-- Step 20 · Bronze -> silver. Bronze is the raw Parquet in the 'landing' container, read through one stage per data
-- product. Silver is typed and de-duplicated, stored as Snowflake-managed Iceberg tables on each product's external
-- volume ('<product>/silver/<table>' in ADLS). Every Iceberg table uses STORAGE_SERIALIZATION_POLICY = COMPATIBLE:
-- the default (OPTIMIZED) only guarantees Snowflake can read the files, and it can't be changed after creation.
-- Silver renames 'date' columns (sales_date, calendar_date) so no engine trips over the keyword. Idempotent.

-- 1. Can Snowflake reach each external volume? Look for "success":true (else re-check scripts/50 role assignments).
USE ROLE ACCOUNTADMIN;
USE WAREHOUSE {{WAREHOUSE}};
SELECT SYSTEM$VERIFY_EXTERNAL_VOLUME('EV_CONTOSO_CORE') AS core_volume;
SELECT SYSTEM$VERIFY_EXTERNAL_VOLUME('EV_CONTOSO_COMMERCIAL') AS commercial_volume;
SELECT SYSTEM$VERIFY_EXTERNAL_VOLUME('EV_CONTOSO_LOYALTY') AS loyalty_volume;

-- 2. Core --------------------------------------------------------------------------------------------------------------
USE ROLE CORE_OWNER;
CREATE FILE FORMAT IF NOT EXISTS CORE.BRONZE.FF_PARQUET TYPE = PARQUET USE_LOGICAL_TYPE = TRUE;
CREATE STAGE IF NOT EXISTS CORE.BRONZE.LANDING
  URL = 'azure://{{STORAGE_ACCOUNT}}.blob.core.windows.net/{{LANDING_CONTAINER}}/core/'
  STORAGE_INTEGRATION = SI_CONTOSO_LANDING
  FILE_FORMAT = CORE.BRONZE.FF_PARQUET
  COMMENT = 'Bronze: raw Parquet for the core data product';
LIST @CORE.BRONZE.LANDING;

CREATE OR REPLACE ICEBERG TABLE CORE.SILVER.DIM_DATE (
  date_key INT, calendar_date DATE, day_of_week INT, day_name STRING, week_start_date DATE, iso_year INT,
  iso_week INT, month_num INT, month_name STRING, quarter_num INT, year_num INT, is_weekend BOOLEAN, holiday_name STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_CORE' BASE_LOCATION = 'silver/dim_date'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
AS SELECT $1:date_key::INT, $1:date::DATE, $1:day_of_week::INT, $1:day_name::STRING, $1:week_start_date::DATE,
          $1:iso_year::INT, $1:iso_week::INT, $1:month::INT, $1:month_name::STRING, $1:quarter::INT, $1:year::INT,
          $1:is_weekend::BOOLEAN, $1:holiday_name::STRING
   FROM @CORE.BRONZE.LANDING/dim_date.parquet
   QUALIFY ROW_NUMBER() OVER (PARTITION BY $1:date_key::INT ORDER BY METADATA$FILE_ROW_NUMBER DESC) = 1;

CREATE OR REPLACE ICEBERG TABLE CORE.SILVER.DIM_STORE (
  store_id STRING, store_name STRING, store_format STRING, city STRING, state STRING, region STRING, dc_id STRING,
  sqft INT, open_date DATE)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_CORE' BASE_LOCATION = 'silver/dim_store'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
AS SELECT $1:store_id::STRING, $1:store_name::STRING, $1:store_format::STRING, $1:city::STRING, $1:state::STRING,
          $1:region::STRING, $1:dc_id::STRING, $1:sqft::INT, $1:open_date::DATE
   FROM @CORE.BRONZE.LANDING/dim_store.parquet
   QUALIFY ROW_NUMBER() OVER (PARTITION BY $1:store_id::STRING ORDER BY METADATA$FILE_ROW_NUMBER DESC) = 1;

CREATE OR REPLACE ICEBERG TABLE CORE.SILVER.DIM_DC (
  dc_id STRING, dc_name STRING, city STRING, state STRING, region STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_CORE' BASE_LOCATION = 'silver/dim_dc'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
AS SELECT $1:dc_id::STRING, $1:dc_name::STRING, $1:city::STRING, $1:state::STRING, $1:region::STRING
   FROM @CORE.BRONZE.LANDING/dim_dc.parquet
   QUALIFY ROW_NUMBER() OVER (PARTITION BY $1:dc_id::STRING ORDER BY METADATA$FILE_ROW_NUMBER DESC) = 1;

CREATE OR REPLACE ICEBERG TABLE CORE.SILVER.DIM_SUPPLIER (
  supplier_id STRING, supplier_name STRING, category STRING, hq_city STRING, hq_state STRING, avg_lead_time_days INT)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_CORE' BASE_LOCATION = 'silver/dim_supplier'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
AS SELECT $1:supplier_id::STRING, $1:supplier_name::STRING, $1:category::STRING, $1:hq_city::STRING,
          $1:hq_state::STRING, $1:avg_lead_time_days::INT
   FROM @CORE.BRONZE.LANDING/dim_supplier.parquet
   QUALIFY ROW_NUMBER() OVER (PARTITION BY $1:supplier_id::STRING ORDER BY METADATA$FILE_ROW_NUMBER DESC) = 1;

CREATE OR REPLACE ICEBERG TABLE CORE.SILVER.DIM_PRODUCT (
  sku STRING, product_name STRING, brand STRING, category STRING, subcategory STRING, supplier_id STRING,
  is_private_label BOOLEAN, unit_price DECIMAL(10,2), unit_cost DECIMAL(10,2), case_pack INT, status STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_CORE' BASE_LOCATION = 'silver/dim_product'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
AS SELECT $1:sku::STRING, $1:product_name::STRING, $1:brand::STRING, $1:category::STRING, $1:subcategory::STRING,
          $1:supplier_id::STRING, $1:is_private_label::BOOLEAN, $1:unit_price::DECIMAL(10,2),
          $1:unit_cost::DECIMAL(10,2), $1:case_pack::INT, $1:status::STRING
   FROM @CORE.BRONZE.LANDING/dim_product.parquet
   QUALIFY ROW_NUMBER() OVER (PARTITION BY $1:sku::STRING ORDER BY METADATA$FILE_ROW_NUMBER DESC) = 1;

-- 3. Commercial --------------------------------------------------------------------------------------------------------
USE ROLE COMMERCIAL_OWNER;
CREATE FILE FORMAT IF NOT EXISTS COMMERCIAL.BRONZE.FF_PARQUET TYPE = PARQUET USE_LOGICAL_TYPE = TRUE;
CREATE STAGE IF NOT EXISTS COMMERCIAL.BRONZE.LANDING
  URL = 'azure://{{STORAGE_ACCOUNT}}.blob.core.windows.net/{{LANDING_CONTAINER}}/commercial/'
  STORAGE_INTEGRATION = SI_CONTOSO_LANDING
  FILE_FORMAT = COMMERCIAL.BRONZE.FF_PARQUET
  COMMENT = 'Bronze: raw Parquet for the commercial data product';
LIST @COMMERCIAL.BRONZE.LANDING;

CREATE OR REPLACE ICEBERG TABLE COMMERCIAL.SILVER.FACT_SALES_DAILY (
  sales_date DATE, store_id STRING, sku STRING, units_sold INT, gross_sales DECIMAL(12,2),
  discount_amount DECIMAL(12,2), net_sales DECIMAL(12,2), cogs DECIMAL(12,2), gross_margin DECIMAL(12,2),
  promo_id STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_COMMERCIAL' BASE_LOCATION = 'silver/fact_sales_daily'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
AS SELECT $1:date::DATE, $1:store_id::STRING, $1:sku::STRING, $1:units_sold::INT, $1:gross_sales::DECIMAL(12,2),
          $1:discount_amount::DECIMAL(12,2), $1:net_sales::DECIMAL(12,2), $1:cogs::DECIMAL(12,2),
          $1:gross_margin::DECIMAL(12,2), $1:promo_id::STRING
   FROM @COMMERCIAL.BRONZE.LANDING/fact_sales_daily.parquet
   QUALIFY ROW_NUMBER() OVER (PARTITION BY $1:date::DATE, $1:store_id::STRING, $1:sku::STRING ORDER BY METADATA$FILE_ROW_NUMBER DESC) = 1;

CREATE OR REPLACE ICEBERG TABLE COMMERCIAL.SILVER.DIM_PROMOTION (
  promo_id STRING, promo_name STRING, promo_type STRING, discount_pct DECIMAL(5,2), start_date DATE, end_date DATE,
  region_scope STRING, category STRING, subcategory STRING, expected_lift_pct INT, funding_type STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_COMMERCIAL' BASE_LOCATION = 'silver/dim_promotion'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
AS SELECT $1:promo_id::STRING, $1:promo_name::STRING, $1:promo_type::STRING, $1:discount_pct::DECIMAL(5,2),
          $1:start_date::DATE, $1:end_date::DATE, $1:region_scope::STRING, $1:category::STRING,
          $1:subcategory::STRING, $1:expected_lift_pct::INT, $1:funding_type::STRING
   FROM @COMMERCIAL.BRONZE.LANDING/dim_promotion.parquet
   QUALIFY ROW_NUMBER() OVER (PARTITION BY $1:promo_id::STRING ORDER BY METADATA$FILE_ROW_NUMBER DESC) = 1;

CREATE OR REPLACE ICEBERG TABLE COMMERCIAL.SILVER.BRIDGE_PROMOTION_SKU (promo_id STRING, sku STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_COMMERCIAL' BASE_LOCATION = 'silver/bridge_promotion_sku'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
AS SELECT DISTINCT $1:promo_id::STRING, $1:sku::STRING
   FROM @COMMERCIAL.BRONZE.LANDING/bridge_promotion_sku.parquet;

CREATE OR REPLACE ICEBERG TABLE COMMERCIAL.SILVER.FIELD_NOTES (
  note_id STRING, note_ts TIMESTAMP_NTZ(6), note_date DATE, region STRING, store_id STRING, author_role STRING,
  topic STRING, promo_id STRING, note_text STRING)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_COMMERCIAL' BASE_LOCATION = 'silver/field_notes'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
AS SELECT $1:note_id::STRING, $1:note_ts::TIMESTAMP_NTZ(6), $1:note_date::DATE, $1:region::STRING,
          $1:store_id::STRING, $1:author_role::STRING, $1:topic::STRING, $1:promo_id::STRING, $1:note_text::STRING
   FROM @COMMERCIAL.BRONZE.LANDING/field_notes.parquet
   QUALIFY ROW_NUMBER() OVER (PARTITION BY $1:note_id::STRING ORDER BY METADATA$FILE_ROW_NUMBER DESC) = 1;

-- 4. Loyalty -----------------------------------------------------------------------------------------------------------
USE ROLE LOYALTY_OWNER;
CREATE FILE FORMAT IF NOT EXISTS LOYALTY.BRONZE.FF_PARQUET TYPE = PARQUET USE_LOGICAL_TYPE = TRUE;
CREATE STAGE IF NOT EXISTS LOYALTY.BRONZE.LANDING
  URL = 'azure://{{STORAGE_ACCOUNT}}.blob.core.windows.net/{{LANDING_CONTAINER}}/loyalty/'
  STORAGE_INTEGRATION = SI_CONTOSO_LANDING
  FILE_FORMAT = LOYALTY.BRONZE.FF_PARQUET
  COMMENT = 'Bronze: raw Parquet for the loyalty data product (contains PII)';
LIST @LOYALTY.BRONZE.LANDING;

CREATE OR REPLACE ICEBERG TABLE LOYALTY.SILVER.DIM_MEMBER (
  member_id STRING, first_name STRING, last_name STRING, email STRING, phone STRING, birth_year INT,
  loyalty_tier STRING, join_date DATE, home_store_id STRING, home_region STRING, marketing_opt_in BOOLEAN)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_LOYALTY' BASE_LOCATION = 'silver/dim_member'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
AS SELECT $1:member_id::STRING, $1:first_name::STRING, $1:last_name::STRING, $1:email::STRING, $1:phone::STRING,
          $1:birth_year::INT, $1:loyalty_tier::STRING, $1:join_date::DATE, $1:home_store_id::STRING,
          $1:home_region::STRING, $1:marketing_opt_in::BOOLEAN
   FROM @LOYALTY.BRONZE.LANDING/dim_member.parquet
   QUALIFY ROW_NUMBER() OVER (PARTITION BY $1:member_id::STRING ORDER BY METADATA$FILE_ROW_NUMBER DESC) = 1;

CREATE OR REPLACE ICEBERG TABLE LOYALTY.SILVER.FACT_MEMBER_WEEKLY (
  week_start_date DATE, member_id STRING, home_store_id STRING, visits INT, net_sales DECIMAL(12,2),
  beverage_sales DECIMAL(12,2), promo_redemptions INT)
  CATALOG = 'SNOWFLAKE' EXTERNAL_VOLUME = 'EV_CONTOSO_LOYALTY' BASE_LOCATION = 'silver/fact_member_weekly'
  STORAGE_SERIALIZATION_POLICY = COMPATIBLE
AS SELECT $1:week_start_date::DATE, $1:member_id::STRING, $1:home_store_id::STRING, $1:visits::INT,
          $1:net_sales::DECIMAL(12,2), $1:beverage_sales::DECIMAL(12,2), $1:promo_redemptions::INT
   FROM @LOYALTY.BRONZE.LANDING/fact_member_weekly.parquet
   QUALIFY ROW_NUMBER() OVER (PARTITION BY $1:week_start_date::DATE, $1:member_id::STRING ORDER BY METADATA$FILE_ROW_NUMBER DESC) = 1;

-- 5. Row counts (expected: dim_date 196 · dim_store 48 · sales 1,539,740 · members 20,000 · member weeks 282,043).
USE ROLE ACCOUNTADMIN;
SELECT 'CORE.SILVER.DIM_DATE' AS table_name, COUNT(*) AS row_count FROM CORE.SILVER.DIM_DATE
UNION ALL SELECT 'CORE.SILVER.DIM_STORE', COUNT(*) FROM CORE.SILVER.DIM_STORE
UNION ALL SELECT 'CORE.SILVER.DIM_DC', COUNT(*) FROM CORE.SILVER.DIM_DC
UNION ALL SELECT 'CORE.SILVER.DIM_SUPPLIER', COUNT(*) FROM CORE.SILVER.DIM_SUPPLIER
UNION ALL SELECT 'CORE.SILVER.DIM_PRODUCT', COUNT(*) FROM CORE.SILVER.DIM_PRODUCT
UNION ALL SELECT 'COMMERCIAL.SILVER.FACT_SALES_DAILY', COUNT(*) FROM COMMERCIAL.SILVER.FACT_SALES_DAILY
UNION ALL SELECT 'COMMERCIAL.SILVER.DIM_PROMOTION', COUNT(*) FROM COMMERCIAL.SILVER.DIM_PROMOTION
UNION ALL SELECT 'COMMERCIAL.SILVER.BRIDGE_PROMOTION_SKU', COUNT(*) FROM COMMERCIAL.SILVER.BRIDGE_PROMOTION_SKU
UNION ALL SELECT 'COMMERCIAL.SILVER.FIELD_NOTES', COUNT(*) FROM COMMERCIAL.SILVER.FIELD_NOTES
UNION ALL SELECT 'LOYALTY.SILVER.DIM_MEMBER', COUNT(*) FROM LOYALTY.SILVER.DIM_MEMBER
UNION ALL SELECT 'LOYALTY.SILVER.FACT_MEMBER_WEEKLY', COUNT(*) FROM LOYALTY.SILVER.FACT_MEMBER_WEEKLY;
