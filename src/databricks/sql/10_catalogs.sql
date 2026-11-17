-- Step 10 · Data products as catalogs. Databricks is the only writer of demand_forecast and supply_chain, each with its
-- own managed storage container. Bronze = external volume over this product's folder in the landing container.
-- @requires DF_URL, SC_URL, LANDING_URL

CREATE CATALOG IF NOT EXISTS demand_forecast MANAGED LOCATION '{{DF_URL}}'
  COMMENT 'Data product: weekly demand forecast by store and SKU (Databricks writes)';
CREATE CATALOG IF NOT EXISTS supply_chain MANAGED LOCATION '{{SC_URL}}'
  COMMENT 'Data product: store inventory and supplier purchase orders (Databricks writes)';

CREATE SCHEMA IF NOT EXISTS demand_forecast.bronze COMMENT 'Raw Parquet landing files';
CREATE SCHEMA IF NOT EXISTS demand_forecast.silver COMMENT 'Typed and de-duplicated';
CREATE SCHEMA IF NOT EXISTS demand_forecast.gold COMMENT 'Data product tables and governed views (Genie: Demand Forecast)';
CREATE SCHEMA IF NOT EXISTS supply_chain.bronze COMMENT 'Raw Parquet landing files';
CREATE SCHEMA IF NOT EXISTS supply_chain.silver COMMENT 'Typed and de-duplicated';
CREATE SCHEMA IF NOT EXISTS supply_chain.gold COMMENT 'Data product tables and governed views (Genie: Supply Chain)';

CREATE EXTERNAL VOLUME IF NOT EXISTS demand_forecast.bronze.landing LOCATION '{{LANDING_URL}}demand_forecast/'
  COMMENT 'Bronze: landing/demand_forecast (read-only external location)';
CREATE EXTERNAL VOLUME IF NOT EXISTS supply_chain.bronze.landing LOCATION '{{LANDING_URL}}supply_chain/'
  COMMENT 'Bronze: landing/supply_chain (read-only external location)';

LIST '/Volumes/demand_forecast/bronze/landing/';
LIST '/Volumes/supply_chain/bronze/landing/';
