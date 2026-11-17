-- Step 61 (fallback, optional) · Snowflake-issued OAuth for the Foundry MCP connections - only if spike S2 shows the
-- Entra token path (step 60) doesn't work end to end. Skipped by the runner until the redirect URL exists:
--   1. Create the custom OAuth connection in the Foundry portal; copy the redirect URL it shows.
--   2. scripts/40-entra-identity.ps1 -RedirectUri <url>   (records it in state/outputs.json)
--   3. python snowflake/run_snowflake.py --only 61
--   4. In Snowsight: SELECT SYSTEM$SHOW_OAUTH_CLIENT_SECRETS('OAUTH_FOUNDRY_MCP');  -> client id/secret for Foundry
--      (not run here, so secrets never land in a log). Auth URL https://{{SNOWFLAKE_HOST}}/oauth/authorize ,
--      token URL https://{{SNOWFLAKE_HOST}}/oauth/token-request , scope: refresh_token
-- @requires FOUNDRY_OAUTH_REDIRECT_URI, SNOWFLAKE_HOST
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE SECURITY INTEGRATION OAUTH_FOUNDRY_MCP
  TYPE = OAUTH
  ENABLED = TRUE
  OAUTH_CLIENT = CUSTOM
  OAUTH_CLIENT_TYPE = 'CONFIDENTIAL'
  OAUTH_REDIRECT_URI = '{{FOUNDRY_OAUTH_REDIRECT_URI}}'
  OAUTH_ISSUE_REFRESH_TOKENS = TRUE
  OAUTH_REFRESH_TOKEN_VALIDITY = 86400
  COMMENT = 'Fallback for spike S2: Snowflake-issued tokens for the Foundry MCP connections';

DESC SECURITY INTEGRATION OAUTH_FOUNDRY_MCP;
