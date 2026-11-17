-- Step 75 · Field-notes search, one Cortex Search service per region (agent trap 7).
-- Cortex Search runs with the OWNER's rights: row access on FIELD_NOTES is NOT applied to whoever queries the service.
-- One index over all notes would hand Ben (East) the West notes about PO-4471. So each region gets its own service
-- (its notes + company-wide 'All' notes) and USAGE goes only to that region's role; HQ gets all four. The Commercial
-- agent lists all four tools and, with tool_not_accessible: accept, silently uses only the ones the caller can access.
-- A service needs change tracking on its source, so the row access policy on FIELD_NOTES must not contain a subquery
-- (step 40). The services build directly on the Iceberg table (verified 2026-10-17).

USE ROLE COMMERCIAL_OWNER;
USE WAREHOUSE {{WAREHOUSE}};

CREATE OR REPLACE CORTEX SEARCH SERVICE COMMERCIAL.GOLD.CSS_FIELD_NOTES_WEST
  ON note_text
  ATTRIBUTES region, store_id, topic, promo_id, author_role
  WAREHOUSE = {{WAREHOUSE}}
  TARGET_LAG = '1 day'
  COMMENT = 'West + company-wide field notes. USAGE: ANALYST_WEST, ANALYST_HQ only.'
  AS (SELECT note_id, note_text, note_date, note_ts, region, store_id, topic, promo_id, author_role
      FROM COMMERCIAL.GOLD.FIELD_NOTES WHERE region IN ('West', 'All'));

CREATE OR REPLACE CORTEX SEARCH SERVICE COMMERCIAL.GOLD.CSS_FIELD_NOTES_EAST
  ON note_text
  ATTRIBUTES region, store_id, topic, promo_id, author_role
  WAREHOUSE = {{WAREHOUSE}}
  TARGET_LAG = '1 day'
  COMMENT = 'East + company-wide field notes. USAGE: ANALYST_EAST, ANALYST_HQ only.'
  AS (SELECT note_id, note_text, note_date, note_ts, region, store_id, topic, promo_id, author_role
      FROM COMMERCIAL.GOLD.FIELD_NOTES WHERE region IN ('East', 'All'));

CREATE OR REPLACE CORTEX SEARCH SERVICE COMMERCIAL.GOLD.CSS_FIELD_NOTES_CENTRAL
  ON note_text
  ATTRIBUTES region, store_id, topic, promo_id, author_role
  WAREHOUSE = {{WAREHOUSE}}
  TARGET_LAG = '1 day'
  COMMENT = 'Central + company-wide field notes. USAGE: ANALYST_HQ only (no Central persona in the demo).'
  AS (SELECT note_id, note_text, note_date, note_ts, region, store_id, topic, promo_id, author_role
      FROM COMMERCIAL.GOLD.FIELD_NOTES WHERE region IN ('Central', 'All'));

CREATE OR REPLACE CORTEX SEARCH SERVICE COMMERCIAL.GOLD.CSS_FIELD_NOTES_SOUTH
  ON note_text
  ATTRIBUTES region, store_id, topic, promo_id, author_role
  WAREHOUSE = {{WAREHOUSE}}
  TARGET_LAG = '1 day'
  COMMENT = 'South + company-wide field notes. USAGE: ANALYST_HQ only (no South persona in the demo).'
  AS (SELECT note_id, note_text, note_date, note_ts, region, store_id, topic, promo_id, author_role
      FROM COMMERCIAL.GOLD.FIELD_NOTES WHERE region IN ('South', 'All'));

-- Per-region roles only - never DATA_READER, which every persona shares.
GRANT USAGE ON CORTEX SEARCH SERVICE COMMERCIAL.GOLD.CSS_FIELD_NOTES_WEST TO ROLE ANALYST_WEST;
GRANT USAGE ON CORTEX SEARCH SERVICE COMMERCIAL.GOLD.CSS_FIELD_NOTES_EAST TO ROLE ANALYST_EAST;
GRANT USAGE ON CORTEX SEARCH SERVICE COMMERCIAL.GOLD.CSS_FIELD_NOTES_WEST TO ROLE ANALYST_HQ;
GRANT USAGE ON CORTEX SEARCH SERVICE COMMERCIAL.GOLD.CSS_FIELD_NOTES_EAST TO ROLE ANALYST_HQ;
GRANT USAGE ON CORTEX SEARCH SERVICE COMMERCIAL.GOLD.CSS_FIELD_NOTES_CENTRAL TO ROLE ANALYST_HQ;
GRANT USAGE ON CORTEX SEARCH SERVICE COMMERCIAL.GOLD.CSS_FIELD_NOTES_SOUTH TO ROLE ANALYST_HQ;

SHOW CORTEX SEARCH SERVICES IN SCHEMA COMMERCIAL.GOLD;

-- Smoke test (expect West notes about Northwind / PO-4471 / empty shelves / rain checks).
SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW('COMMERCIAL.GOLD.CSS_FIELD_NOTES_WEST',
  '{"query": "why were promo shelves empty", "columns": ["note_id", "note_date", "store_id", "topic"], "limit": 3}')):results AS west_results;
