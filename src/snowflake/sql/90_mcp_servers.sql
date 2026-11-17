-- Step 90 · Snowflake-managed MCP servers - one per data product (decision D4b), plus design A for the comparison.
--   MCP_COMMERCIAL_AGENT  design B: only the Commercial Analyst agent (CORTEX_AGENT_RUN)
--   MCP_LOYALTY_AGENT     design B: only the Loyalty Analyst agent
--   MCP_COMMERCIAL_SQL    design A: semantic view (CORTEX_ANALYST_MESSAGE) + read-only SQL on its own warehouse.
--                         A separate server, as Snowflake recommends: a SQL tool next to an agent is a side door.
-- MCP grants don't cascade: callers need USAGE on the server AND on each tool's object (agent, semantic view).
-- @requires CORTEX_AGENT_MODEL, SNOWFLAKE_HOST

USE ROLE COMMERCIAL_OWNER;
CREATE OR REPLACE MCP SERVER COMMERCIAL.GOLD.MCP_COMMERCIAL_AGENT
  FROM SPECIFICATION $$
tools:
  - name: "commercial-analyst"
    type: "CORTEX_AGENT_RUN"
    identifier: "COMMERCIAL.GOLD.COMMERCIAL_ANALYST"
    title: "Contoso Commercial Analyst"
    description: "Answers questions about sales, promotions and store field notes, for the regions the signed-in user may see. Ask complete business questions."
$$;
GRANT USAGE ON MCP SERVER COMMERCIAL.GOLD.MCP_COMMERCIAL_AGENT TO ROLE DATA_READER;

CREATE OR REPLACE MCP SERVER COMMERCIAL.GOLD.MCP_COMMERCIAL_SQL
  FROM SPECIFICATION $$
tools:
  - name: "commercial-semantic-view"
    type: "CORTEX_ANALYST_MESSAGE"
    identifier: "COMMERCIAL.GOLD.SV_COMMERCIAL"
    title: "Commercial semantic view"
    description: "Turns a business question about sales and promotions into SQL over the commercial semantic view. Returns the SQL; it does not run it."
  - name: "run-sql"
    type: "SYSTEM_EXECUTE_SQL"
    title: "Run read-only SQL"
    description: "Runs one read-only SELECT statement on Snowflake as the signed-in user and returns the rows."
    config:
      read_only: true
      query_timeout: 60
      warehouse: "WH_CONTOSO_MCP_SQL"
$$;
GRANT USAGE ON MCP SERVER COMMERCIAL.GOLD.MCP_COMMERCIAL_SQL TO ROLE DATA_READER;

USE ROLE LOYALTY_OWNER;
CREATE OR REPLACE MCP SERVER LOYALTY.GOLD.MCP_LOYALTY_AGENT
  FROM SPECIFICATION $$
tools:
  - name: "loyalty-analyst"
    type: "CORTEX_AGENT_RUN"
    identifier: "LOYALTY.GOLD.LOYALTY_ANALYST"
    title: "Contoso Loyalty Analyst"
    description: "Answers questions about loyalty members' visits, tiers and spend, aggregated by region and tier, for the regions the signed-in user may see."
$$;
GRANT USAGE ON MCP SERVER LOYALTY.GOLD.MCP_LOYALTY_AGENT TO ROLE LOYALTY_READER;

-- Endpoints for Foundry (hyphenated host - MCP clients break on underscores).
SELECT 'MCP_COMMERCIAL_AGENT' AS server, 'https://{{SNOWFLAKE_HOST}}/api/v2/databases/COMMERCIAL/schemas/GOLD/mcp-servers/MCP_COMMERCIAL_AGENT' AS url
UNION ALL SELECT 'MCP_COMMERCIAL_SQL', 'https://{{SNOWFLAKE_HOST}}/api/v2/databases/COMMERCIAL/schemas/GOLD/mcp-servers/MCP_COMMERCIAL_SQL'
UNION ALL SELECT 'MCP_LOYALTY_AGENT', 'https://{{SNOWFLAKE_HOST}}/api/v2/databases/LOYALTY/schemas/GOLD/mcp-servers/MCP_LOYALTY_AGENT';
