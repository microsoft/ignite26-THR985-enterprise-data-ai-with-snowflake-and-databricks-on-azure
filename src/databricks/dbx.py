"""Databricks helpers: clients (Azure CLI auth - no tokens to store), template variables, and a small SQL runner on
the Statement Execution API. Every SQL statement is fully qualified, because each API call is its own session."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from databricks.sdk import AccountClient, WorkspaceClient
from databricks.sdk.service import sql as dbsql

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import poc_common as pc  # noqa: E402

CONNECTION = "snowflake_contoso"
CREDENTIAL = "cred_contoso_adls"
DONE = (dbsql.StatementState.SUCCEEDED, dbsql.StatementState.FAILED, dbsql.StatementState.CANCELED,
        dbsql.StatementState.CLOSED)


def workspace() -> WorkspaceClient:
    url = pc.state().get("databricksWorkspaceUrl")
    if not url:
        sys.exit("No workspace URL in state - run scripts/55-databricks-workspace.ps1 first.")
    pc.assert_personal_tenant()
    return WorkspaceClient(host=url, auth_type="azure-cli")


def account() -> AccountClient:
    account_id = pc.settings()["databricks"].get("accountId")
    if not account_id:
        sys.exit("Set databricks.accountId in config/settings.json (copy it from https://accounts.azuredatabricks.net).")
    pc.assert_personal_tenant()
    return AccountClient(host="https://accounts.azuredatabricks.net", account_id=account_id, auth_type="azure-cli")


def abfss(container: str, path: str = "") -> str:
    return f"abfss://{container}@{pc.state()['storageAccountName']}.dfs.core.windows.net/{path}"


def variables() -> dict:
    s, st = pc.settings(), pc.state()
    c, groups = s["containers"], s["entra"]["groups"]
    account = (s["snowflake"].get("account") or "").lower()
    v = {
        "STORAGE_ACCOUNT": st.get("storageAccountName"),
        "LANDING_URL": abfss(c["landing"]) if st.get("storageAccountName") else None,
        "DF_URL": abfss(c["databricksProducts"][0]) if st.get("storageAccountName") else None,
        "SC_URL": abfss(c["databricksProducts"][1]) if st.get("storageAccountName") else None,
        "GROUP_WEST": groups["West"], "GROUP_EAST": groups["East"], "GROUP_CENTRAL": groups["Central"],
        "GROUP_SOUTH": groups["South"], "GROUP_HQ": groups["All"], "GROUP_ADMINS": s["entra"]["adminGroup"],
        "SNOWFLAKE_HOST": f"{account.replace('_', '-')}.snowflakecomputing.com" if account else None,
        "WAREHOUSE_ID": st.get("databricksWarehouseId"),
    }
    v.update(pc.demo_values())
    return v


def warehouse_id() -> str:
    wid = pc.state().get("databricksWarehouseId")
    if not wid:
        sys.exit("No SQL warehouse in state - run python databricks/setup_platform.py first.")
    return wid


def run_sql(w: WorkspaceClient, statement: str, wid: str | None = None, timeout_s: int = 900):
    """Runs one statement and waits for it. Returns (column names, rows as lists of strings)."""
    resp = w.statement_execution.execute_statement(
        statement=statement, warehouse_id=wid or warehouse_id(), wait_timeout="30s",
        on_wait_timeout=dbsql.ExecuteStatementRequestOnWaitTimeout.CONTINUE)
    deadline = time.time() + timeout_s
    while resp.status.state not in DONE:
        if time.time() > deadline:
            w.statement_execution.cancel_execution(resp.statement_id)
            raise TimeoutError(f"statement still running after {timeout_s} s - cancelled")
        time.sleep(2)
        resp = w.statement_execution.get_statement(resp.statement_id)
    if resp.status.state != dbsql.StatementState.SUCCEEDED:
        err = resp.status.error.message if resp.status.error else str(resp.status.state)
        raise RuntimeError(err)
    cols = [col.name for col in resp.manifest.schema.columns] if resp.manifest and resp.manifest.schema else []
    data = resp.result.data_array if resp.result and resp.result.data_array else []
    return cols, data


def pem_body(text: str) -> str:
    """Databricks wants the unencrypted PKCS8 key without header, footer or line breaks."""
    return re.sub(r"-----[A-Z ]+-----|\s", "", text)


def fed_private_key() -> str:
    path = pc.ROOT / ".secrets" / "snowflake_fed_rsa_key.p8"
    if path.exists():
        return pem_body(path.read_text())
    vault = pc.state().get("keyVaultUri")
    if not vault:
        sys.exit("No federation key - run python snowflake/keys.py first.")
    pc.assert_personal_tenant()
    from azure.identity import AzureCliCredential
    from azure.keyvault.secrets import SecretClient
    return pem_body(SecretClient(vault_url=vault, credential=AzureCliCredential())
                    .get_secret("snowflake-fed-private-key").value)
