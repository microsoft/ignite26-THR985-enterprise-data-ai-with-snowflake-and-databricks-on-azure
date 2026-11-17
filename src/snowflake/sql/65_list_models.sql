-- Step 65 · Which models can this account call (Azure East US 2, cross-region = {{CORTEX_CROSS_REGION}})?
-- Lists the models that run in this region or through the cross-region scope. Cortex Agents accept only some of them:
-- with AZURE_US, openai-gpt-5.4, -5.2, -5.1, -5 and -5-mini (checked 2026-10-17; Claude and Gemini need ANY_REGION).
-- Current list: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents (Models).
-- Pin one in config/settings.json > snowflake.cortexAgentModel (no 'auto': the demo must be repeatable), then
-- continue with step 70. Steps 80+ are skipped until the model is set.
USE ROLE ACCOUNTADMIN;
USE WAREHOUSE {{WAREHOUSE}};
SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION' IN ACCOUNT;
-- The refresh takes several minutes (7-10 on the PoC account, every run): it re-registers every model as an object.
CALL SNOWFLAKE.MODELS.CORTEX_BASE_MODELS_REFRESH();
SHOW CORTEX BASE MODELS IN SCHEMA SNOWFLAKE.MODELS
->> SELECT "name" AS model, "lifecycle_status" AS status,
           IFF(ARRAY_CONTAINS(CURRENT_REGION()::VARIANT, "in_region_availability"), 'in region', 'cross-region') AS runs,
           "eol_date" AS end_of_life
      FROM $1
     WHERE "lifecycle_status" <> 'EOL'
       AND (ARRAY_CONTAINS(CURRENT_REGION()::VARIANT, "in_region_availability")
            OR ARRAYS_OVERLAP(SPLIT('{{CORTEX_CROSS_REGION}}', ','), "cross_region_availability"))
     ORDER BY runs, model;
