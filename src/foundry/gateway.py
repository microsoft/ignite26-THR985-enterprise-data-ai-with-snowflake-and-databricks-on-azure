#!/usr/bin/env python3
"""README step F4 helper - puts the Part B data-product calls behind the AI gateway, so Control Plane can block them.

  python foundry/gateway.py                             # every endpoint registered in Control Plane
  python foundry/gateway.py --only contoso-commercial
  python foundry/gateway.py --direct                    # back to calling Snowflake and Databricks directly

Registering an MCP endpoint in Control Plane (Operate > Register asset, Agent name = the tool label, for example
contoso-commercial) creates an API, tagged 'agent', in the AI gateway's API Management instance. Foundry sends an MCP
tool's calls to the URL stored in the tool's project connection, not to the tool's server URL. So this script points
each custom-OAuth connection at its gateway URL. Credentials and the redirect URL stay as they are, so nobody has to
consent again. Safe to re-run. Then run python foundry/agents.py --only contoso-orchestrator.

The commercial connection is shared with design B, so design B goes through the gateway too.
"""
import argparse
import json
import sys

import fdy
import requests
from azure.identity import AzureCliCredential

pc = fdy.pc
ARM = "https://management.azure.com"
CONNECTIONS_API, APIM_API = "2025-06-01", "2024-05-01"
ROUTED = ["commercialAgent", "loyaltyAgent", "demandForecast", "supplyChain"]  # the Part B data-product agents
KEEP = ("authType", "category", "group", "metadata", "authorizationUrl", "tokenUrl", "refreshUrl", "scopes",
        "connectorName", "redirectUrl", "isSharedToAll", "useCustomConnector", "useWorkspaceManagedIdentity",
        "peRequirement")


def arm(s: requests.Session, method: str, path: str, api: str, body: dict | None = None) -> dict:
    r = s.request(method, ARM + path, params={"api-version": api}, json=body, timeout=60)
    if r.status_code >= 400:
        sys.exit(f"{method} {path}: HTTP {r.status_code} {r.text[:300]}")
    return json.loads(r.content.decode("utf-8-sig")) if r.content else {}


def gateway_urls(s: requests.Session, resource_group_id: str) -> dict:
    """Agent name -> gateway URL, for every API that Control Plane registered (tagged 'agent')."""
    urls = {}
    for svc in arm(s, "GET", f"{resource_group_id}/providers/Microsoft.ApiManagement/service", APIM_API).get("value", []):
        for api in arm(s, "GET", svc["id"] + "/apis", APIM_API).get("value", []):
            tags = {t["name"] for t in arm(s, "GET", api["id"] + "/tags", APIM_API).get("value", [])}
            if "agent" in tags:
                urls[api["properties"]["displayName"]] = f"{svc['properties']['gatewayUrl']}/{api['properties']['path']}"
    return urls


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="tool labels, for example contoso-commercial")
    ap.add_argument("--direct", action="store_true", help="point the connections back at Snowflake and Databricks")
    args = ap.parse_args()
    fdy.endpoint()  # project exists, personal tenant
    st, names, specs = pc.state(), pc.settings()["foundry"]["connections"], fdy.tool_specs()
    s = requests.Session()
    s.headers["Authorization"] = "Bearer " + AzureCliCredential().get_token(ARM + "/.default").token
    gateway = {} if args.direct else gateway_urls(s, st["foundryAccountId"].split("/providers/")[0])

    pc.banner("Foundry MCP connections -> " + ("Snowflake and Databricks (direct)" if args.direct else "AI gateway"))
    for key in ROUTED:
        spec, name = specs[key], names[key]
        if args.only and spec["label"] not in args.only:
            continue
        target = spec["url"] if args.direct else gateway.get(spec["label"])
        if not target:
            print(f"    {spec['label']}: not registered in Control Plane yet (Agent name '{spec['label']}') - stays as is")
            continue
        path = f"{st['foundryProjectId']}/connections/{name}"
        p = arm(s, "GET", path, CONNECTIONS_API)["properties"]
        if p.get("target") == target:
            print(f"    {name}: already {target}")
            continue
        cred = arm(s, "POST", path + "/listsecrets", CONNECTIONS_API)["properties"]["credentials"]
        # Read-modify-write: resend what the portal stored, with only the target replaced.
        props = {k: p[k] for k in KEEP if k in p}
        props.update(target=target, sharedUserList=p.get("sharedUserList") or [],
                     credentials={"clientId": cred["clientId"], "clientSecret": cred["clientSecret"]})
        arm(s, "PUT", path, CONNECTIONS_API, {"properties": props})
        after = arm(s, "GET", path, CONNECTIONS_API)["properties"]
        note = "" if after.get("redirectUrl") == p.get("redirectUrl") else \
            f"\n      WARNING: redirect URL changed to {after.get('redirectUrl')} - add it with 40-entra-identity.ps1"
        print(f"    {name}: {p.get('target')}\n      -> {after.get('target')}{note}")
    print("\nNext: python foundry/agents.py --only contoso-orchestrator, then python foundry/chat.py --as ava --check")


if __name__ == "__main__":
    main()
