#!/usr/bin/env python3
"""Databricks OAuth for Foundry - FALLBACK for spike S2, only if Foundry refuses to pass Entra tokens for Azure
Databricks to the Genie MCP endpoint ("Cannot pass Microsoft token to untrusted MCP endpoint"). Creates a confidential
account-level custom OAuth app; Databricks then issues the tokens (still per person, so row filters still apply).

  1. In the Foundry portal create the custom OAuth connection for a Genie MCP tool; copy its redirect URL.
  2. python databricks/oauth_fallback.py --redirect-uri <url>
  3. Paste the client ID, the secret (from Key Vault) and the endpoints printed below into that Foundry connection.
"""
import argparse

import dbx

pc = dbx.pc
NAME = "contoso-foundry-genie-mcp"


def to_key_vault(name: str, value: str) -> None:
    from azure.identity import AzureCliCredential
    from azure.keyvault.secrets import SecretClient
    SecretClient(vault_url=pc.state()["keyVaultUri"], credential=AzureCliCredential()).set_secret(name, value)
    print(f"    stored {name} in Key Vault")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--redirect-uri", required=True, help="redirect URL shown by the Foundry OAuth connection")
    args = ap.parse_args()
    a, host = dbx.account(), pc.state()["databricksWorkspaceUrl"]

    existing = [i for i in a.custom_app_integration.list() if i.name == NAME]
    if existing:
        a.custom_app_integration.update(existing[0].integration_id, redirect_urls=[args.redirect_uri])
        print(f"    {NAME} exists ({existing[0].client_id}) - redirect URL updated; secret unchanged in Key Vault")
        client_id = existing[0].client_id
    else:
        out = a.custom_app_integration.create(name=NAME, confidential=True, redirect_urls=[args.redirect_uri],
                                              scopes=["all-apis", "offline_access"])
        client_id = out.client_id
        to_key_vault("databricks-oauth-client-id", out.client_id)
        to_key_vault("databricks-oauth-client-secret", out.client_secret)
        print(f"    created {NAME} ({client_id})")
    pc.update_state({"databricksOAuthClientId": client_id})
    print("\nFoundry custom OAuth connection values:")
    print(f"    client ID       {client_id}   (secret: Key Vault databricks-oauth-client-secret)")
    print(f"    authorize URL   {host}/oidc/v1/authorize")
    print(f"    token URL       {host}/oidc/v1/token")
    print(f"    refresh URL     {host}/oidc/v1/token")
    print("    scopes          all-apis offline_access")


if __name__ == "__main__":
    main()
