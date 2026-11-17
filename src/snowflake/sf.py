"""Snowflake connection (key-pair auth) and the template variables used by the SQL files."""
import sys
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import poc_common as pc  # noqa: E402


def connect(role: str | None = None):
    cfg = pc.settings()["snowflake"]
    if not cfg.get("account") or not cfg.get("adminUser"):
        sys.exit("Fill config/settings.json > snowflake.account and snowflake.adminUser first.")
    key_path = pc.ROOT / cfg["privateKeyPath"]
    if not key_path.exists():
        sys.exit("No admin key - run: python snowflake/keys.py (then the ALTER USER it prints).")
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    der = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    # Default warehouse: the admin user has none, and a run resumed at any file must still be able to run queries.
    return snowflake.connector.connect(account=cfg["account"], user=cfg["adminUser"], private_key=der,
                                       role=role or cfg.get("adminRole", "ACCOUNTADMIN"),
                                       warehouse=cfg.get("warehouse"), client_session_keep_alive=False)


def variables() -> dict:
    s, st = pc.settings(), pc.state()
    sf = s["snowflake"]
    domain = s["entra"]["domain"] or st.get("entraDomain", "")
    users = {u["alias"].upper(): u for u in s["entra"]["users"]}
    account = (sf.get("account") or "").lower()
    v = {
        "STORAGE_ACCOUNT": st.get("storageAccountName"),
        "LANDING_CONTAINER": s["containers"]["landing"],
        "TENANT_ID": st.get("tenantId"),
        "WAREHOUSE": sf["warehouse"],
        "CORTEX_CROSS_REGION": sf["cortexCrossRegion"],
        "CORTEX_AGENT_MODEL": sf.get("cortexAgentModel"),
        "MONTHLY_CREDITS": s["budget"]["snowflakeMonthlyCredits"],
        "ADMIN_USER": sf["adminUser"],
        "FED_USER_PUBLIC_KEY": st.get("snowflake_fed_public_key"),
        "EXTERNAL_OAUTH_AUDIENCE": st.get("snowflakeResourceAppIdUri"),
        "FOUNDRY_OAUTH_REDIRECT_URI": st.get("foundryOAuthRedirectUri"),
        # MCP clients break on underscores in host names - Snowflake accepts the hyphenated form.
        "SNOWFLAKE_HOST": f"{account.replace('_', '-')}.snowflakecomputing.com" if account else None,
    }
    v.update(pc.demo_values())
    for alias, u in users.items():
        v[f"UPN_{alias}"] = f"{u['alias']}@{domain}" if domain else None
    return v
