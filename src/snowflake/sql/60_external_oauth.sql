-- Step 60 · Snowflake trusts Entra ID tokens (External OAuth). Foundry's OAuth identity passthrough gets a token for
-- the signed-in person with scope api://<snowflake-app>/session:role-any; Snowflake maps its 'upn' claim to the
-- user's LOGIN_NAME and opens the session with that user's DEFAULT role. ACCOUNTADMIN, ORGADMIN and SECURITYADMIN
-- stay blocked for OAuth by default.
-- @requires TENANT_ID, EXTERNAL_OAUTH_AUDIENCE
USE ROLE ACCOUNTADMIN;

-- Issuer: v1 tokens (sts.windows.net) - the documented default for the resource app created by 40-entra-identity.ps1.
CREATE OR REPLACE SECURITY INTEGRATION EXT_OAUTH_ENTRA
  TYPE = EXTERNAL_OAUTH
  ENABLED = TRUE
  EXTERNAL_OAUTH_TYPE = AZURE
  EXTERNAL_OAUTH_ISSUER = 'https://sts.windows.net/{{TENANT_ID}}/'
  EXTERNAL_OAUTH_JWS_KEYS_URL = 'https://login.microsoftonline.com/{{TENANT_ID}}/discovery/v2.0/keys'
  EXTERNAL_OAUTH_AUDIENCE_LIST = ('{{EXTERNAL_OAUTH_AUDIENCE}}')
  EXTERNAL_OAUTH_TOKEN_USER_MAPPING_CLAIM = 'upn'
  EXTERNAL_OAUTH_SNOWFLAKE_USER_MAPPING_ATTRIBUTE = 'login_name'
  EXTERNAL_OAUTH_ANY_ROLE_MODE = 'ENABLE'
  COMMENT = 'Entra ID tokens from the Foundry MCP client app (scope session:role-any = the user''s default role)';

DESC SECURITY INTEGRATION EXT_OAUTH_ENTRA;
