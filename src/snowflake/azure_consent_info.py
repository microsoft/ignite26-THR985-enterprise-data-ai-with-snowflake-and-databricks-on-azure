#!/usr/bin/env python3
"""Reads the Azure consent URL and multi-tenant app name for the landing storage integration and the three external
volumes, and writes them to state/outputs.json (snowflakeAzureApps) for scripts/50-snowflake-consent.ps1."""
import json
import re

import sf

pc = sf.pc
OBJECTS = [
    ("STORAGE INTEGRATION", "SI_CONTOSO_LANDING", "landing", "Storage Blob Data Reader"),
    ("EXTERNAL VOLUME", "EV_CONTOSO_CORE", "core", "Storage Blob Data Contributor"),
    ("EXTERNAL VOLUME", "EV_CONTOSO_COMMERCIAL", "commercial", "Storage Blob Data Contributor"),
    ("EXTERNAL VOLUME", "EV_CONTOSO_LOYALTY", "loyalty", "Storage Blob Data Contributor"),
]
KEYS = ("AZURE_CONSENT_URL", "AZURE_MULTI_TENANT_APP_NAME")


def find_values(rows: list[dict]) -> dict:
    """Properties appear either as their own rows or inside a JSON value (external volume storage locations)."""
    found = {}
    for r in rows:
        prop, val = str(r.get("property", "")).upper(), r.get("property_value")
        if prop in KEYS:
            found[prop] = val
        elif isinstance(val, str) and "AZURE_" in val:
            try:
                blob = json.loads(val)
                for k in KEYS:
                    if blob.get(k):
                        found[k] = blob[k]
            except json.JSONDecodeError:
                for k in KEYS:
                    m = re.search(rf'"{k}"\s*:\s*"([^"]+)"', val)
                    if m:
                        found[k] = m.group(1)
    return found


def main() -> None:
    conn = sf.connect()
    cur = conn.cursor(sf.snowflake.connector.DictCursor)
    apps = []
    try:
        for kind, name, container, role in OBJECTS:
            cur.execute(f"DESC {kind} {name}")
            rows = [{k.lower(): v for k, v in row.items()} for row in cur.fetchall()]
            vals = find_values(rows)
            if not all(k in vals for k in KEYS):
                raise SystemExit(f"Could not read {KEYS} from DESC {kind} {name} - run snowflake/sql/10_storage.sql first.")
            apps.append({"object": name, "container": container, "role": role,
                         "consentUrl": vals["AZURE_CONSENT_URL"], "appName": vals["AZURE_MULTI_TENANT_APP_NAME"]})
            print(f"{name}: {vals['AZURE_MULTI_TENANT_APP_NAME']}")
    finally:
        cur.close()
        conn.close()
    pc.update_state({"snowflakeAzureApps": apps})
    print("\nWritten to state/outputs.json - next: scripts/50-snowflake-consent.ps1")


if __name__ == "__main__":
    main()
