#!/usr/bin/env python3
"""Databricks step D1 - platform objects in Unity Catalog (idempotent, run as the workspace admin via Azure CLI):

  * serverless SQL warehouse - every SQL step, Genie and the federated reads run on it
  * storage credential from the Access Connector's managed identity
  * external locations: landing (read-only), the Databricks product containers, uc-federation, and Snowflake's
    core + commercial containers (read-only: Snowflake is their only writer)
  * Snowflake connection as SVC_DATABRICKS_FED (key pair) - created through the API so the private key never
    appears in a SQL statement or query history (war story B)
  * foreign catalogs sf_core and sf_commercial with CATALOG FEDERATION: Databricks reads the Iceberg files directly;
    authorized paths are the gold/ folders only; metadata cache in the uc-federation container

  python databricks/setup_platform.py
"""
import sys
import time

import dbx
from databricks.sdk.errors import DatabricksError, NotFound
from databricks.sdk.service import catalog
from databricks.sdk.service import sql as dbsql

pc = dbx.pc
FOREIGN = (("sf_core", "CORE", "core"), ("sf_commercial", "COMMERCIAL", "commercial"))


def retry(fn, what: str, attempts: int = 6, delay: int = 30):
    """Storage RBAC can take minutes to reach the Access Connector - retry validation failures."""
    for n in range(1, attempts + 1):
        try:
            return fn()
        except DatabricksError as e:
            if n == attempts:
                raise
            print(f"    {what}: {str(e).splitlines()[0][:140]} - retrying in {delay} s ({n}/{attempts})")
            time.sleep(delay)


def ensure_warehouse(w) -> str:
    name = pc.settings()["databricks"]["warehouseName"]
    for wh in w.warehouses.list():
        if wh.name == name:
            print(f"    warehouse {name} exists ({wh.id})")
            return wh.id
    # Serverless needs warehouse_type PRO + enable_serverless_compute (SDK docs).
    wh = w.warehouses.create(
        name=name, cluster_size="2X-Small", min_num_clusters=1, max_num_clusters=1, auto_stop_mins=10,
        warehouse_type=dbsql.CreateWarehouseRequestWarehouseType.PRO, enable_serverless_compute=True).result()
    print(f"    created serverless warehouse {name} ({wh.id})")
    return wh.id


def ensure_credential(w) -> None:
    try:
        w.storage_credentials.get(dbx.CREDENTIAL)
        print(f"    storage credential {dbx.CREDENTIAL} exists")
        return
    except NotFound:
        pass
    w.storage_credentials.create(
        name=dbx.CREDENTIAL,
        azure_managed_identity=catalog.AzureManagedIdentityRequest(access_connector_id=pc.state()["accessConnectorId"]),
        comment="Access Connector managed identity - writes only the Databricks containers (Azure RBAC)")
    print(f"    created storage credential {dbx.CREDENTIAL}")


def ensure_locations(w) -> None:
    c = pc.settings()["containers"]
    df, sc = c["databricksProducts"]
    wanted = [
        ("ext_landing", c["landing"], True, "Bronze: raw Parquet landing files (read-only)"),
        ("ext_demand_forecast", df, False, "Managed storage of the demand_forecast catalog (Databricks writes)"),
        ("ext_supply_chain", sc, False, "Managed storage of the supply_chain catalog (Databricks writes)"),
        ("ext_uc_federation", c["databricksPlatform"], False, "Metadata cache for the Snowflake foreign catalogs"),
        ("ext_sf_core", "core", True, "Snowflake core data product - read-only, Snowflake is the only writer"),
        ("ext_sf_commercial", "commercial", True, "Snowflake commercial data product - read-only"),
    ]
    for name, container, read_only, comment in wanted:
        try:
            w.external_locations.get(name)
            print(f"    external location {name} exists")
            continue
        except NotFound:
            pass
        retry(lambda: w.external_locations.create(name=name, url=dbx.abfss(container), credential_name=dbx.CREDENTIAL,
                                                  read_only=read_only, comment=comment), name)
        print(f"    created external location {name} -> {dbx.abfss(container)}{' (read-only)' if read_only else ''}")


def ensure_connection(w) -> None:
    v = dbx.variables()
    if not v["SNOWFLAKE_HOST"]:
        sys.exit("Set snowflake.account in config/settings.json.")
    options = {"host": v["SNOWFLAKE_HOST"], "port": "443", "sfWarehouse": "WH_CONTOSO_FED",
               "user": "SVC_DATABRICKS_FED", "pem_private_key": dbx.fed_private_key()}
    try:
        w.connections.get(dbx.CONNECTION)
        w.connections.update(name=dbx.CONNECTION, options=options)
        print(f"    connection {dbx.CONNECTION} exists - key and options refreshed")
    except NotFound:
        w.connections.create(name=dbx.CONNECTION, connection_type=catalog.ConnectionType.SNOWFLAKE, options=options,
                             comment="Snowflake as SVC_DATABRICKS_FED / FED_READER (gold core + commercial only)")
        print(f"    created connection {dbx.CONNECTION} -> {v['SNOWFLAKE_HOST']}")


def ensure_foreign_catalogs(w, wid: str) -> None:
    ucf = pc.settings()["containers"]["databricksPlatform"]
    for name, database, container in FOREIGN:
        try:
            cat = w.catalogs.get(name)
            print(f"    foreign catalog {name} exists (options: {cat.options}, storage root: {cat.storage_root})")
            continue
        except NotFound:
            pass
        authorized, root = dbx.abfss(container, "gold/"), dbx.abfss(ucf, f"{name}/")
        comment = f"Snowflake {database} via catalog federation - direct Iceberg reads, gold only"
        # The SQL option names follow Databricks' own Snowflake-interop guidance; the API form is the fallback.
        sql = (f"CREATE FOREIGN CATALOG IF NOT EXISTS {name} USING CONNECTION {dbx.CONNECTION} COMMENT '{comment}' "
               f"OPTIONS (database '{database}', authorized_paths '{authorized}', storage_root '{root}')")
        try:
            dbx.run_sql(w, sql, wid)
        except Exception as e:  # noqa: BLE001
            print(f"    SQL form failed ({str(e).splitlines()[0][:120]}) - trying the API form")
            try:
                w.catalogs.create(name=name, connection_name=dbx.CONNECTION, comment=comment, storage_root=root,
                                  options={"database": database, "authorized_paths": authorized})
            except DatabricksError as e2:
                sys.exit(f"Could not create {name}: {e2}\nCreate it in Catalog Explorer (Add data > Foreign catalog): "
                         f"connection {dbx.CONNECTION}, database {database}, authorized path {authorized}, "
                         f"storage location {root}. Then re-run this script.")
        cat = w.catalogs.get(name)
        print(f"    created foreign catalog {name} (options: {cat.options}, storage root: {cat.storage_root})")


def verify_federation(w, wid: str) -> None:
    """Catalog federation falls back to query federation (JDBC) without an error when it can't use a table's Iceberg
    metadata - for example when FED_READER lacks USAGE on the external volume. The answers stay the same, so check
    the provider: 'iceberg' = direct read, 'snowflake' = JDBC, with a Snowflake warehouse running every read."""
    for name, _, _ in FOREIGN:
        dbx.run_sql(w, f"REFRESH FOREIGN CATALOG {name}", wid)
    jdbc = []
    for table in ("sf_core.gold.dim_store", "sf_commercial.gold.fact_sales_daily"):
        _, data = dbx.run_sql(w, f"DESCRIBE TABLE EXTENDED {table}", wid)
        info = {r[0]: r[1] for r in data if r and r[0]}
        provider = str(info.get("Provider") or info.get("Type") or "?")
        print(f"    {table} provider: {provider}")
        if "iceberg" not in provider.lower():
            jdbc.append(table)
    _, data = dbx.run_sql(w, "SELECT COUNT(*) FROM sf_commercial.gold.fact_sales_daily", wid)
    print(f"    rows in Snowflake's Iceberg table: {data[0][0]} (expected 1539740)")
    if jdbc:
        sys.exit(f"\nQuery federation (JDBC) instead of catalog federation for {', '.join(jdbc)}. Check that FED_READER "
                 "has USAGE on the external volumes (snowflake/sql/10_storage.sql) and that the Iceberg files are "
                 "under the catalog's authorized paths, then re-run this script (it refreshes the foreign catalogs).")


def main() -> None:
    w = dbx.workspace()
    pc.banner("SQL warehouse")
    wid = ensure_warehouse(w)
    pc.update_state({"databricksWarehouseId": wid})
    pc.banner("Storage credential and external locations")
    ensure_credential(w)
    ensure_locations(w)
    pc.banner("Snowflake connection and foreign catalogs (catalog federation)")
    ensure_connection(w)
    ensure_foreign_catalogs(w, wid)
    verify_federation(w, wid)
    pc.update_state({"databricksConnection": dbx.CONNECTION, "databricksForeignCatalogs": [f[0] for f in FOREIGN]})
    print("\nNext: python databricks/setup_account.py")


if __name__ == "__main__":
    main()
