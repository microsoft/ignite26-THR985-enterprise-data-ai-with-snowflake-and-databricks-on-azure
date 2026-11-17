-- Step 40 · Access: row filters on the gold tables and grants for the reader groups (Entra groups brought in by
-- setup_account.py). Readers get gold only - never silver, bronze or the sf_* foreign catalogs: the governed views
-- read Snowflake with the view owner's rights and filter rows by the caller's group.
-- Row filters apply everywhere the table is read - SQL editor, Genie, and the Genie MCP server Foundry calls.

ALTER TABLE demand_forecast.gold.forecast_weekly SET ROW FILTER demand_forecast.gold.rf_region ON (region);
ALTER TABLE supply_chain.gold.inventory_daily SET ROW FILTER supply_chain.gold.rf_region ON (region);
ALTER TABLE supply_chain.gold.supplier_po SET ROW FILTER supply_chain.gold.rf_region ON (region);

-- {{GROUP_WEST}}
GRANT USE CATALOG ON CATALOG demand_forecast TO `{{GROUP_WEST}}`;
GRANT USE SCHEMA ON SCHEMA demand_forecast.gold TO `{{GROUP_WEST}}`;
GRANT SELECT ON SCHEMA demand_forecast.gold TO `{{GROUP_WEST}}`;
GRANT EXECUTE ON FUNCTION demand_forecast.gold.rf_region TO `{{GROUP_WEST}}`;
GRANT USE CATALOG ON CATALOG supply_chain TO `{{GROUP_WEST}}`;
GRANT USE SCHEMA ON SCHEMA supply_chain.gold TO `{{GROUP_WEST}}`;
GRANT SELECT ON SCHEMA supply_chain.gold TO `{{GROUP_WEST}}`;
GRANT EXECUTE ON FUNCTION supply_chain.gold.rf_region TO `{{GROUP_WEST}}`;

-- {{GROUP_EAST}}
GRANT USE CATALOG ON CATALOG demand_forecast TO `{{GROUP_EAST}}`;
GRANT USE SCHEMA ON SCHEMA demand_forecast.gold TO `{{GROUP_EAST}}`;
GRANT SELECT ON SCHEMA demand_forecast.gold TO `{{GROUP_EAST}}`;
GRANT EXECUTE ON FUNCTION demand_forecast.gold.rf_region TO `{{GROUP_EAST}}`;
GRANT USE CATALOG ON CATALOG supply_chain TO `{{GROUP_EAST}}`;
GRANT USE SCHEMA ON SCHEMA supply_chain.gold TO `{{GROUP_EAST}}`;
GRANT SELECT ON SCHEMA supply_chain.gold TO `{{GROUP_EAST}}`;
GRANT EXECUTE ON FUNCTION supply_chain.gold.rf_region TO `{{GROUP_EAST}}`;

-- {{GROUP_CENTRAL}}
GRANT USE CATALOG ON CATALOG demand_forecast TO `{{GROUP_CENTRAL}}`;
GRANT USE SCHEMA ON SCHEMA demand_forecast.gold TO `{{GROUP_CENTRAL}}`;
GRANT SELECT ON SCHEMA demand_forecast.gold TO `{{GROUP_CENTRAL}}`;
GRANT EXECUTE ON FUNCTION demand_forecast.gold.rf_region TO `{{GROUP_CENTRAL}}`;
GRANT USE CATALOG ON CATALOG supply_chain TO `{{GROUP_CENTRAL}}`;
GRANT USE SCHEMA ON SCHEMA supply_chain.gold TO `{{GROUP_CENTRAL}}`;
GRANT SELECT ON SCHEMA supply_chain.gold TO `{{GROUP_CENTRAL}}`;
GRANT EXECUTE ON FUNCTION supply_chain.gold.rf_region TO `{{GROUP_CENTRAL}}`;

-- {{GROUP_SOUTH}}
GRANT USE CATALOG ON CATALOG demand_forecast TO `{{GROUP_SOUTH}}`;
GRANT USE SCHEMA ON SCHEMA demand_forecast.gold TO `{{GROUP_SOUTH}}`;
GRANT SELECT ON SCHEMA demand_forecast.gold TO `{{GROUP_SOUTH}}`;
GRANT EXECUTE ON FUNCTION demand_forecast.gold.rf_region TO `{{GROUP_SOUTH}}`;
GRANT USE CATALOG ON CATALOG supply_chain TO `{{GROUP_SOUTH}}`;
GRANT USE SCHEMA ON SCHEMA supply_chain.gold TO `{{GROUP_SOUTH}}`;
GRANT SELECT ON SCHEMA supply_chain.gold TO `{{GROUP_SOUTH}}`;
GRANT EXECUTE ON FUNCTION supply_chain.gold.rf_region TO `{{GROUP_SOUTH}}`;

-- {{GROUP_HQ}}
GRANT USE CATALOG ON CATALOG demand_forecast TO `{{GROUP_HQ}}`;
GRANT USE SCHEMA ON SCHEMA demand_forecast.gold TO `{{GROUP_HQ}}`;
GRANT SELECT ON SCHEMA demand_forecast.gold TO `{{GROUP_HQ}}`;
GRANT EXECUTE ON FUNCTION demand_forecast.gold.rf_region TO `{{GROUP_HQ}}`;
GRANT USE CATALOG ON CATALOG supply_chain TO `{{GROUP_HQ}}`;
GRANT USE SCHEMA ON SCHEMA supply_chain.gold TO `{{GROUP_HQ}}`;
GRANT SELECT ON SCHEMA supply_chain.gold TO `{{GROUP_HQ}}`;
GRANT EXECUTE ON FUNCTION supply_chain.gold.rf_region TO `{{GROUP_HQ}}`;

SHOW GRANTS ON SCHEMA demand_forecast.gold;
