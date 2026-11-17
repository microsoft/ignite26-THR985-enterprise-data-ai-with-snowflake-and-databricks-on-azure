-- Step 10 · Storage: one storage integration for the landing (bronze) container, and one external volume per
-- Snowflake data product on the dfs endpoint (required for Unity Catalog interop - war story A).
-- After this file: run scripts/50-snowflake-consent.ps1 (admin consent + storage RBAC), then continue with 20.
USE ROLE ACCOUNTADMIN;

CREATE STORAGE INTEGRATION IF NOT EXISTS SI_CONTOSO_LANDING
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'AZURE'
  ENABLED = TRUE
  AZURE_TENANT_ID = '{{TENANT_ID}}'
  STORAGE_ALLOWED_LOCATIONS = ('azure://{{STORAGE_ACCOUNT}}.blob.core.windows.net/{{LANDING_CONTAINER}}/')
  COMMENT = 'Bronze: raw Parquet landing files (read only)';

CREATE EXTERNAL VOLUME IF NOT EXISTS EV_CONTOSO_CORE
  STORAGE_LOCATIONS = ((
    NAME = 'core-eastus2'
    STORAGE_PROVIDER = 'AZURE'
    STORAGE_BASE_URL = 'azure://{{STORAGE_ACCOUNT}}.dfs.core.windows.net/core/'
    AZURE_TENANT_ID = '{{TENANT_ID}}'))
  ALLOW_WRITES = TRUE
  COMMENT = 'Core data product - Snowflake is the only writer';

CREATE EXTERNAL VOLUME IF NOT EXISTS EV_CONTOSO_COMMERCIAL
  STORAGE_LOCATIONS = ((
    NAME = 'commercial-eastus2'
    STORAGE_PROVIDER = 'AZURE'
    STORAGE_BASE_URL = 'azure://{{STORAGE_ACCOUNT}}.dfs.core.windows.net/commercial/'
    AZURE_TENANT_ID = '{{TENANT_ID}}'))
  ALLOW_WRITES = TRUE
  COMMENT = 'Commercial data product - Snowflake is the only writer';

CREATE EXTERNAL VOLUME IF NOT EXISTS EV_CONTOSO_LOYALTY
  STORAGE_LOCATIONS = ((
    NAME = 'loyalty-eastus2'
    STORAGE_PROVIDER = 'AZURE'
    STORAGE_BASE_URL = 'azure://{{STORAGE_ACCOUNT}}.dfs.core.windows.net/loyalty/'
    AZURE_TENANT_ID = '{{TENANT_ID}}'))
  ALLOW_WRITES = TRUE
  COMMENT = 'Loyalty data product - Snowflake is the only writer';

GRANT USAGE ON INTEGRATION SI_CONTOSO_LANDING TO ROLE CORE_OWNER;
GRANT USAGE ON INTEGRATION SI_CONTOSO_LANDING TO ROLE COMMERCIAL_OWNER;
GRANT USAGE ON INTEGRATION SI_CONTOSO_LANDING TO ROLE LOYALTY_OWNER;
GRANT USAGE ON EXTERNAL VOLUME EV_CONTOSO_CORE       TO ROLE CORE_OWNER;
GRANT USAGE ON EXTERNAL VOLUME EV_CONTOSO_COMMERCIAL TO ROLE COMMERCIAL_OWNER;
GRANT USAGE ON EXTERNAL VOLUME EV_CONTOSO_LOYALTY    TO ROLE LOYALTY_OWNER;
-- Databricks catalog federation (step D1) looks up each table's Iceberg metadata as FED_READER, which needs USAGE on
-- the table's external volume. Without it Databricks silently falls back to query federation over JDBC: the same
-- answers, but every read runs on a Snowflake warehouse too. USAGE alone can't create tables (FED_READER has no CREATE
-- privilege anywhere), and Databricks reads the files with its own read-only storage credential.
GRANT USAGE ON EXTERNAL VOLUME EV_CONTOSO_CORE       TO ROLE FED_READER;
GRANT USAGE ON EXTERNAL VOLUME EV_CONTOSO_COMMERCIAL TO ROLE FED_READER;

-- Consent URLs and multi-tenant app names - exported to state/ by snowflake/azure_consent_info.py.
DESC STORAGE INTEGRATION SI_CONTOSO_LANDING;
DESC EXTERNAL VOLUME EV_CONTOSO_CORE;
