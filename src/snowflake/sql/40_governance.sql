-- Step 40 · Governance, owned by GOVERNANCE_ADMIN (separation of duties: product owners can't change policies).
--   * RAP_REGION: one row access policy for every regional table. The role -> region rules are written in the policy
--     itself (no mapping-table lookup), so Cortex Search can index FIELD_NOTES - see the note at the policy.
--     Region 'All' (company-wide field notes) is visible to everyone who can read the table.
--   * Masking on loyalty PII: only LOYALTY_STEWARD (and the product owner) see clear values.
-- Policies are re-attached on every run (DROP ALL + ADD), so this file is safe to re-run after step 30.

USE ROLE GOVERNANCE_ADMIN;
USE WAREHOUSE {{WAREHOUSE}};

-- Cortex Search (step 75) needs change tracking on its source, and change tracking rejects a row access policy that
-- contains ANY subquery: the usual mapping-table lookup (EXISTS or IN), even wrapped in a memoizable function (tested
-- 2026-10-17). So the rules are plain IS_ROLE_IN_SESSION checks, which also count inherited roles:
--   * every region: HQ analysts, the loyalty steward, admins, the product owners - COMMERCIAL_OWNER builds the
--     per-region search services, which index what the owner sees - and FED_READER (Databricks narrows access again
--     with its own governed views, war story B)
--   * one region: ANALYST_WEST (Ava), ANALYST_EAST (Ben)
-- The argument is named row_region so it can't be confused with a column name.
CREATE ROW ACCESS POLICY IF NOT EXISTS GOVERNANCE.POLICIES.RAP_REGION AS (row_region STRING) RETURNS BOOLEAN -> FALSE;
ALTER ROW ACCESS POLICY GOVERNANCE.POLICIES.RAP_REGION SET BODY ->
  row_region = 'All'
  OR IS_ROLE_IN_SESSION('ANALYST_HQ')
  OR IS_ROLE_IN_SESSION('LOYALTY_STEWARD')
  OR IS_ROLE_IN_SESSION('CONTOSO_ADMIN')
  OR IS_ROLE_IN_SESSION('CORE_OWNER')
  OR IS_ROLE_IN_SESSION('COMMERCIAL_OWNER')
  OR IS_ROLE_IN_SESSION('LOYALTY_OWNER')
  OR IS_ROLE_IN_SESSION('FED_READER')
  OR (row_region = 'West' AND IS_ROLE_IN_SESSION('ANALYST_WEST'))
  OR (row_region = 'East' AND IS_ROLE_IN_SESSION('ANALYST_EAST'));
ALTER ROW ACCESS POLICY GOVERNANCE.POLICIES.RAP_REGION SET COMMENT = 'Rows by region; rules in the body (no subquery, so Cortex Search can index FIELD_NOTES)';
-- Earlier versions of this file looked the rules up in a mapping table.
DROP TABLE IF EXISTS GOVERNANCE.POLICIES.REGION_ROLE_MAP;

CREATE MASKING POLICY IF NOT EXISTS GOVERNANCE.POLICIES.MASK_PII_TEXT AS (val STRING) RETURNS STRING -> val;
ALTER MASKING POLICY GOVERNANCE.POLICIES.MASK_PII_TEXT SET BODY ->
  CASE WHEN IS_ROLE_IN_SESSION('LOYALTY_STEWARD') OR IS_ROLE_IN_SESSION('LOYALTY_OWNER') THEN val
       ELSE '*** masked ***' END;

CREATE MASKING POLICY IF NOT EXISTS GOVERNANCE.POLICIES.MASK_EMAIL AS (val STRING) RETURNS STRING -> val;
ALTER MASKING POLICY GOVERNANCE.POLICIES.MASK_EMAIL SET BODY ->
  CASE WHEN IS_ROLE_IN_SESSION('LOYALTY_STEWARD') OR IS_ROLE_IN_SESSION('LOYALTY_OWNER') THEN val
       ELSE REGEXP_REPLACE(val, '^[^@]+', '***') END;

CREATE MASKING POLICY IF NOT EXISTS GOVERNANCE.POLICIES.MASK_PHONE AS (val STRING) RETURNS STRING -> val;
ALTER MASKING POLICY GOVERNANCE.POLICIES.MASK_PHONE SET BODY ->
  CASE WHEN IS_ROLE_IN_SESSION('LOYALTY_STEWARD') OR IS_ROLE_IN_SESSION('LOYALTY_OWNER') THEN val
       ELSE '***-' || RIGHT(val, 4) END;

-- Birth year keeps its type (input and output types must match): everyone else sees the decade.
CREATE MASKING POLICY IF NOT EXISTS GOVERNANCE.POLICIES.MASK_BIRTH_YEAR AS (val NUMBER) RETURNS NUMBER -> val;
ALTER MASKING POLICY GOVERNANCE.POLICIES.MASK_BIRTH_YEAR SET BODY ->
  CASE WHEN IS_ROLE_IN_SESSION('LOYALTY_STEWARD') OR IS_ROLE_IN_SESSION('LOYALTY_OWNER') THEN val
       ELSE FLOOR(val / 10) * 10 END;

-- Attach: row access by region ------------------------------------------------------------------------------------------
-- @may-fail (nothing attached yet after step 30)
ALTER ICEBERG TABLE COMMERCIAL.GOLD.FACT_SALES_DAILY DROP ALL ROW ACCESS POLICIES;
ALTER ICEBERG TABLE COMMERCIAL.GOLD.FACT_SALES_DAILY ADD ROW ACCESS POLICY GOVERNANCE.POLICIES.RAP_REGION ON (region);
-- @may-fail (nothing attached yet after step 30)
ALTER ICEBERG TABLE COMMERCIAL.GOLD.FIELD_NOTES DROP ALL ROW ACCESS POLICIES;
ALTER ICEBERG TABLE COMMERCIAL.GOLD.FIELD_NOTES ADD ROW ACCESS POLICY GOVERNANCE.POLICIES.RAP_REGION ON (region);
-- @may-fail (nothing attached yet after step 30)
ALTER ICEBERG TABLE LOYALTY.GOLD.DIM_MEMBER DROP ALL ROW ACCESS POLICIES;
ALTER ICEBERG TABLE LOYALTY.GOLD.DIM_MEMBER ADD ROW ACCESS POLICY GOVERNANCE.POLICIES.RAP_REGION ON (home_region);
-- @may-fail (nothing attached yet after step 30)
ALTER ICEBERG TABLE LOYALTY.GOLD.FACT_MEMBER_WEEKLY DROP ALL ROW ACCESS POLICIES;
ALTER ICEBERG TABLE LOYALTY.GOLD.FACT_MEMBER_WEEKLY ADD ROW ACCESS POLICY GOVERNANCE.POLICIES.RAP_REGION ON (home_region);

-- Attach: PII masking ----------------------------------------------------------------------------------------------------
ALTER ICEBERG TABLE LOYALTY.GOLD.DIM_MEMBER MODIFY COLUMN first_name SET MASKING POLICY GOVERNANCE.POLICIES.MASK_PII_TEXT FORCE;
ALTER ICEBERG TABLE LOYALTY.GOLD.DIM_MEMBER MODIFY COLUMN last_name SET MASKING POLICY GOVERNANCE.POLICIES.MASK_PII_TEXT FORCE;
ALTER ICEBERG TABLE LOYALTY.GOLD.DIM_MEMBER MODIFY COLUMN email SET MASKING POLICY GOVERNANCE.POLICIES.MASK_EMAIL FORCE;
ALTER ICEBERG TABLE LOYALTY.GOLD.DIM_MEMBER MODIFY COLUMN phone SET MASKING POLICY GOVERNANCE.POLICIES.MASK_PHONE FORCE;
ALTER ICEBERG TABLE LOYALTY.GOLD.DIM_MEMBER MODIFY COLUMN birth_year SET MASKING POLICY GOVERNANCE.POLICIES.MASK_BIRTH_YEAR FORCE;

-- What is attached where (step 95 and check_answers.py test the effect per persona)
SELECT policy_name, policy_kind, ref_entity_name, ref_column_name
FROM TABLE(COMMERCIAL.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => 'COMMERCIAL.GOLD.FACT_SALES_DAILY', REF_ENTITY_DOMAIN => 'table'));
SELECT policy_name, policy_kind, ref_entity_name, ref_column_name
FROM TABLE(LOYALTY.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => 'LOYALTY.GOLD.DIM_MEMBER', REF_ENTITY_DOMAIN => 'table'));
