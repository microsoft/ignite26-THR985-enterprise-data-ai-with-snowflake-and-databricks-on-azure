-- Step 95 · Checks (read-only, safe to re-run). snowflake/check_answers.py compares the numbers with the answer key;
-- this file shows the governance effects per persona. "allowed to fail" lines below are EXPECTED denials.

-- 1. Objects ------------------------------------------------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;
USE WAREHOUSE {{WAREHOUSE}};
SHOW ICEBERG TABLES IN ACCOUNT;
SHOW SEMANTIC VIEWS IN ACCOUNT;
SHOW CORTEX SEARCH SERVICES IN SCHEMA COMMERCIAL.GOLD;
SHOW MCP SERVERS IN SCHEMA COMMERCIAL.GOLD;
SHOW MCP SERVERS IN SCHEMA LOYALTY.GOLD;

-- 2. Ben (East): row access and masking --------------------------------------------------------------------------------
USE ROLE ANALYST_EAST;
USE SECONDARY ROLES NONE;
SELECT 'ANALYST_EAST' AS persona, LISTAGG(DISTINCT region, ',') WITHIN GROUP (ORDER BY region) AS sales_regions_visible
FROM COMMERCIAL.GOLD.FACT_SALES_DAILY;
SELECT 'ANALYST_EAST' AS persona, LISTAGG(DISTINCT region, ',') WITHIN GROUP (ORDER BY region) AS note_regions_visible
FROM COMMERCIAL.GOLD.FIELD_NOTES;
SELECT member_id, first_name, last_name, email, phone, birth_year, home_region FROM LOYALTY.GOLD.DIM_MEMBER LIMIT 3;
SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW('COMMERCIAL.GOLD.CSS_FIELD_NOTES_EAST',
  '{"query": "promo shelves", "columns": ["note_id", "region", "topic"], "limit": 2}')):results AS east_index_ok;
-- @may-fail EXPECTED: Ben has no USAGE on the West index (owner's-rights trap closed)
SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW('COMMERCIAL.GOLD.CSS_FIELD_NOTES_WEST',
  '{"query": "PO-4471", "columns": ["note_id", "region"], "limit": 2}')):results AS west_index_must_fail;

-- 3. Ava (West) ---------------------------------------------------------------------------------------------------------
USE ROLE ANALYST_WEST;
USE SECONDARY ROLES NONE;
SELECT 'ANALYST_WEST' AS persona, LISTAGG(DISTINCT region, ',') WITHIN GROUP (ORDER BY region) AS sales_regions_visible
FROM COMMERCIAL.GOLD.FACT_SALES_DAILY;
SELECT * FROM SEMANTIC_VIEW(COMMERCIAL.GOLD.SV_COMMERCIAL
  DIMENSIONS sales.region METRICS sales.total_units, sales.total_net_sales
  WHERE sales.promo_id = '{{PROMO_ID}}');

-- 4. Cara (HQ): every region, PII still masked -------------------------------------------------------------------------
USE ROLE ANALYST_HQ;
USE SECONDARY ROLES NONE;
SELECT * FROM SEMANTIC_VIEW(COMMERCIAL.GOLD.SV_COMMERCIAL
  DIMENSIONS sales.region METRICS sales.total_units, sales.total_net_sales
  WHERE sales.promo_id = '{{PROMO_ID}}') ORDER BY region;
SELECT member_id, first_name, email FROM LOYALTY.GOLD.DIM_MEMBER LIMIT 2;

-- 5. Federation role: gold core + 3 commercial tables only -------------------------------------------------------------
USE ROLE FED_READER;
USE SECONDARY ROLES NONE;
USE WAREHOUSE WH_CONTOSO_FED;
SELECT COUNT(*) AS fed_sales_rows FROM COMMERCIAL.GOLD.FACT_SALES_DAILY;
-- @may-fail EXPECTED: the federation role can't read field notes or loyalty
SELECT COUNT(*) AS fed_notes_rows_must_fail FROM COMMERCIAL.GOLD.FIELD_NOTES;

-- 6. Cost evidence (ACCOUNT_USAGE lags up to ~3 hours) -----------------------------------------------------------------
USE ROLE ACCOUNTADMIN;
USE SECONDARY ROLES ALL;
USE WAREHOUSE {{WAREHOUSE}};
SELECT warehouse_name, ROUND(SUM(credits_used), 3) AS credits_7d
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE start_time > DATEADD(day, -7, CURRENT_TIMESTAMP()) AND warehouse_name LIKE 'WH_CONTOSO%'
GROUP BY warehouse_name ORDER BY warehouse_name;
-- What did Databricks run here? With catalog federation: metadata calls only; scans here mean query-federation fallback.
SELECT start_time, warehouse_name, query_type, execution_status, LEFT(query_text, 120) AS query_text
FROM TABLE(COMMERCIAL.INFORMATION_SCHEMA.QUERY_HISTORY_BY_USER(USER_NAME => 'SVC_DATABRICKS_FED', RESULT_LIMIT => 25))
ORDER BY start_time DESC;
