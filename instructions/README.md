# Build the proof of concept

Build the proof of concept behind THR985 in your own Azure subscription, Microsoft Entra tenant, Snowflake account and Azure Databricks workspace. Everything is fictional: the company is Contoso, and the data is synthetic and deterministic (seed 42; see the [data generator](../src/data-generator/README.md)).

> [!IMPORTANT]
> - Use a personal or sandbox tenant and subscription, never your organization's. The scripts create users, groups and app registrations, and grant admin consent.
> - The proof of concept costs money while it exists. Check the [prerequisites](#prerequisites), and [clean up](#clean-up) when you're done.
> - Run every command from the [`src`](../src/README.md) folder. All paths below are relative to it.

## What you build
- **Demo 1 — one copy, every engine brings its own compute.** Azure Data Lake Storage holds Iceberg tables with one writer per data product. Snowflake writes `core`, `commercial` and `loyalty`; Databricks writes `demand-forecast` and `supply-chain`. Databricks reads Snowflake's gold tables directly through catalog federation.
- **Demo 2 — agents at the data, governed from Foundry.** Two Snowflake Cortex Agents (Commercial, Loyalty) and two Databricks Genie agents (Demand Forecast, Supply Chain) sit behind one MCP server per data product. Foundry orchestrators call them with OAuth identity passthrough, so Ava (West), Ben (East) and Cara (HQ) each get only their own data.
- **Design A vs B (Demo 2 Part A).** A separate Snowflake MCP server exposes the semantic view plus read-only SQL. `foundry/bench.py` measures it against the Cortex Agent.

## Prerequisites
| | |
|---|---|
| Tools | Windows with PowerShell 7.2+, Azure CLI 2.60+, Python 3.10+ (a `.venv` is created for you), a browser |
| Azure | Personal subscription; you are **Owner**. A spending limit (Visual Studio credit) can stay on: the PoC costs about US$1.20 a day on Azure when idle (mostly the Databricks workspace's NAT gateway), plus Databricks SQL DBUs once you upgrade the workspace to Premium after the 14-day trial (see step 55). The AI gateway is free for up to 100,000 requests when you create it from Foundry (F1). With the limit on, Azure disables the subscription if the credit runs out. |
| Entra | Personal tenant; you are **Global Administrator** (creates users and apps, grants admin consent, first Databricks account admin) |
| Snowflake | **New** trial: **Enterprise**, **Microsoft Azure – East US 2**. Add a **credit card on day 1** (AI features), and convert to on-demand before day 30. |
| Region | Everything in **East US 2** (most Foundry models and features; Cortex runs in-region) |

## Configure
1. Copy `config/settings.example.json` to `config/settings.json`.
2. Fill in `tenantId` (your **personal** Entra tenant ID), `subscriptionId` and `budget.alertEmail`. Add `snowflake.account` (`orgname-accountname`) and `snowflake.adminUser` before phase 4, and `databricks.accountId` after step 55.
3. Sign in with `scripts/login.ps1`. It uses the PoC's own Azure CLI profile (`~/.azure-contoso-thr985`), so your other sign-ins (for example work) stay untouched. Every script, PowerShell and Python, uses that profile and stops if it's signed in to any tenant other than `tenantId`. Keep one terminal for the PoC.

Generated values (names with the random suffix, IDs, URLs) go to `state/outputs.json`. Secrets go to `.secrets/` and Key Vault. All of these are git-ignored.

## Run order (risk-first)
The riskiest parts are in Foundry: OAuth identity passthrough and Control Plane (spikes S2 and S3). So Foundry's base setup runs right after Entra, and a checkpoint (phase 5) tests both on Snowflake alone, before you build Databricks. You can also run F1 and C3 after phase 6: Databricks doesn't need the AI gateway; only phase 7's F4 does.

Every step is idempotent: re-run it after fixing a problem. Python steps use the venv: `.venv\Scripts\python.exe <script>`, shown below as `python`.

| Step | Command | What it does |
|---|---|---|
| **1 · Azure** | | |
| login | `scripts/login.ps1` | Signs in to your personal tenant in the PoC's own Azure CLI profile (see "Configure") |
| 00 | `scripts/00-preflight.ps1` | Checks tools, sign-in and the spending limit; registers providers; creates the venv and the name suffix |
| 10 | `scripts/10-azure-foundation.ps1` | Resource group, Log Analytics + App Insights, Azure Data Lake Storage (hierarchical namespace, shared keys off, 14-day soft delete), containers, Key Vault (**IP allowlist: your IP**), budget alerts |
| 30 | `scripts/30-upload-landing.ps1` | Generates the data and uploads raw Parquet to `landing/` (bronze); copies the answer key to `state/` |
| **2 · Identity** | | |
| 40 | `scripts/40-entra-identity.ps1` | Ava, Ben, Cara (passwords in Key Vault), region + HQ + data-admin groups, Snowflake resource app (`session:role-any`), Foundry MCP client app (secret in Key Vault) |
| **3 · Foundry setup** | | |
| 45 | `scripts/45-foundry.ps1` | Foundry resource + project, gpt-5-mini deployment (version pinned; checks your **quota tier** first), App Insights tracing, roles for you and the personas |
| **4 · Snowflake** | | |
| SF0 | `python snowflake/keys.py` | Key pairs for your Snowflake admin and `SVC_DATABRICKS_FED`. **Run the printed `ALTER USER` once in Snowsight.** |
| SF1 | `python snowflake/run_snowflake.py --only 00 10` | Warehouses (one per consumer), notify-only resource monitor, roles, databases; storage integration + external volumes (`dfs`) |
| SF2 | `python snowflake/azure_consent_info.py` then `scripts/50-snowflake-consent.ps1` | Admin consent for Snowflake's Azure app, then Storage Blob Delegator (account) + data roles (container) for its service principal. Can take up to an hour. |
| SF3 | `python snowflake/run_snowflake.py --only 20 30 40 50 60` | Silver and gold Iceberg tables (`COMPATIBLE`), row access + masking, users, External OAuth (Entra) |
| SF4 | `python snowflake/run_snowflake.py --only 65` | Lists the models this account can call (takes about 10 minutes). **Pin one** that Cortex Agents accept in `snowflake.cortexAgentModel` (see the note in `65_list_models.sql`); the PoC uses `openai-gpt-5-mini`. |
| SF5 | `python snowflake/run_snowflake.py --from 70` | Semantic views, per-region Cortex Search, Cortex Agents, MCP servers, checks |
| SF6 | `python snowflake/check_answers.py` | Numbers vs the answer key; row access, masking and search grants per persona |
| **5 · Checkpoint: test the risky parts on Snowflake alone** | | |
| F2 | Foundry portal | OAuth connections for the three Snowflake MCP servers; add the redirect URLs Foundry shows with `scripts/40-entra-identity.ps1 -RedirectUri <url1>,<url2>`, then run `scripts/foundry-oauth-secret.ps1` |
| F3 | `python foundry/agents.py` | Creates design A and B (`contoso-orchestrator-a`, `-b`); skips `contoso-orchestrator` until Databricks exists |
| C1 | `python foundry/chat.py --as ava`, then `--as ben` | **Spike S2**, OAuth passthrough: Ava's answer covers only the West, Ben's only the East (chat uses design B until Databricks exists) |
| C2 | `python foundry/bench.py --runs 20` | **Spike S5**: design A vs B as Cara (feeds the session's A vs B slide). Runs before the gateway exists, so both designs call Snowflake directly; see "Spike S5" |
| $ | Azure portal | **Optional: remove the spending limit.** This PoC doesn't need it: the AI gateway that F1 creates from Foundry (API Management Basic v2) is free for up to 100,000 requests (the PoC used about 3,500), and the rest costs about US$1.20 a day when idle. Remove it only if you use an existing or separately created API Management instance, which is billed by the hour (Basic v2 about $150/month at list price): **Cost Management + Billing** → **My subscriptions** → your Visual Studio subscription → the banner on the overview → **Remove spending limit indefinitely** → choose the payment method → **Finish**. Some Visual Studio subscriptions don't offer this option. |
| F1 | Foundry portal | AI gateway (API Management Basic v2) and the project added to it; see "Foundry portal steps" |
| C3 | F4 for `MCP_COMMERCIAL_AGENT`, then `python foundry/gateway.py --only contoso-commercial` and `python foundry/agents.py --only contoso-orchestrator` | **Spike S3**: MCP calls through the AI gateway with OAuth passthrough intact; block and unblock the agent in Control Plane |
| **6 · Databricks** | | |
| 55 | `scripts/55-databricks-workspace.ps1` | Access Connector (Delegator at account scope, data roles per container) and the Azure Databricks workspace on the **Trial pricing tier** (Premium features; DBUs free for 14 days). Then open the workspace once and copy the **account ID** into settings. **When the trial ends, compute stops** (warehouses fail with `RESOURCE_EXHAUSTED ... exhausted your available credits`) until you upgrade the workspace to Premium: **Upgrade to Premium** on the workspace in the Azure portal, or `az resource update --ids <workspace resource ID> --set sku.name=premium`. It takes about 2 minutes and keeps everything; DBUs are then billed to the subscription. |
| D1 | `python databricks/setup_platform.py` | Serverless SQL warehouse, storage credential, external locations, Snowflake connection (key pair, via API), **catalog federation** to `sf_core` and `sf_commercial` |
| D2 | `python databricks/setup_account.py` | Entra groups and people in via automatic identity management; workspace access with the **consumer access** entitlement; notify-only budget |
| D3 | `python databricks/run_databricks.py` | Catalogs, bronze volumes, silver, gold (joined to Snowflake's core), governed views over Snowflake's sales, row filters, grants |
| D4 | `python databricks/setup_genie.py` | Genie agents *Contoso Demand Forecast* and *Contoso Supply Chain*, shared with the groups; MCP URLs saved to state. Each space has a curated example SQL for the question the Part B orchestrator asks (`GENIE_QUESTIONS` in `python/poc_common.py`). Turns on the **Managed MCP Servers** preview the MCP endpoints need (workspace setting `managed_mcp_servers`; in the UI: your user name → **Previews**), then calls both endpoints to check they answer. Re-running updates the spaces in place (same IDs and MCP URLs). |
| D5 | `python databricks/check_answers.py` | Federation is direct Iceberg; forecast vs actual, stockouts, PO-4471, lost sales, Northwind history |
| **7 · Finish Foundry** | | |
| F2 | Foundry portal | OAuth connections for the two Genie MCP servers; add their redirect URLs with step 40, then run `scripts/foundry-oauth-secret.ps1` |
| F3 | `python foundry/agents.py` | Now also creates `contoso-orchestrator` (Demo 2 Part B: all four data-product agents) |
| F4 | Foundry portal, then `python foundry/gateway.py` | Register the loyalty and Genie endpoints in Control Plane, point their connections at the gateway, run `agents.py --only contoso-orchestrator` again |
| C4 | `python foundry/chat.py --as ava`, then `ben` and `cara` | Demo 2 Part B end to end; expected answers under "Verification" |
| **Optional** | | |
| 90 | `scripts/90-lockdown-storage.ps1` *(optional)* | Storage firewall experiment; `-Undo` reopens |
| 99 | `scripts/99-teardown.ps1 [-RemoveEntra]` | Deletes the Azure side; Snowflake is dropped by hand |

If C1 fails, work through "If spike S2 fails" below before you build Databricks.

`scripts/allow-my-ip.ps1` refreshes the Key Vault allowlist (and the storage firewall, if it's on) when your public IP changes.

## Foundry portal steps (no CLI/API for these yet)
F2 to F4 are done in two passes: the Snowflake servers at the checkpoint (phase 5), the Genie servers in phase 7.

**F1 · AI gateway**
- In the Foundry portal (new experience), select **Manage → AI Gateway → Add AI Gateway**. Select the Foundry resource, choose **Create new** (API Management Basic v2; the CLI can't create v2 tiers yet), name the gateway and select **Add**. Wait until its status is **Enabled** (5–10 minutes). Created this way, the instance is free for up to 100,000 requests; in 5 days the PoC's billing showed no API Management charges.
- The project existed before the gateway, so add it: select the gateway's name, find `contoso-thr985` and select **Add project to gateway** (Gateway status → **Enabled**). Only projects on a gateway can register custom agents.
- Nothing that works changes: the gateway mediates only MCP tools created after it exists, and our connections are older, so they keep calling Snowflake and Databricks directly until a proxy URL is set (F4).

**F2 · OAuth connections**
- Create one custom-OAuth MCP connection per server (https://ai.azure.com/build/tools → **Connect a tool → Custom → MCP → OAuth Identity Passthrough**), named as in `settings.foundry.connections`. All use client `contoso-foundry-mcp-client` (`foundryClientAppId` in `state/outputs.json`). For the client secret, type any placeholder: `scripts/foundry-oauth-secret.ps1` then writes the real one from Key Vault (`foundry-mcp-client-secret`) into every connection, so the secret is never copied by hand. Authorization URL `https://login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize`; token and refresh URL `…/oauth2/v2.0/token`.

| Connection | Phase | MCP URL (from `run_snowflake.py --only 90` / `setup_genie.py`) | Scopes (space-separated) |
|---|---|---|---|
| snowflake-commercial-agent | 5 | `…/databases/COMMERCIAL/schemas/GOLD/mcp-servers/MCP_COMMERCIAL_AGENT` | `api://<snowflake app id>/session:role-any offline_access` |
| snowflake-commercial-sql | 5 | `…/mcp-servers/MCP_COMMERCIAL_SQL` | same |
| snowflake-loyalty-agent | 5 | `…/databases/LOYALTY/schemas/GOLD/mcp-servers/MCP_LOYALTY_AGENT` | same |
| genie-demand-forecast | 7 | `https://adb-….azuredatabricks.net/api/2.0/mcp/genie/<space id>` | `2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/user_impersonation offline_access` |
| genie-supply-chain | 7 | same pattern | same |

- Foundry shows a redirect URL for each connection. Add them with `scripts/40-entra-identity.ps1 -RedirectUri <url1>,<url2>`; new URLs are added to the existing ones. Then run `scripts/foundry-oauth-secret.ps1` (safe to re-run; it leaves the redirect URLs as they are).

**F3 · Agents**
- `python foundry/agents.py` creates every agent whose connections exist and skips the rest with the reason. At the checkpoint that's design A and B (`contoso-orchestrator-a`, `-b`; Part A and S5, commercial only); in phase 7 it adds `contoso-orchestrator` (Part B: all four data-product agents). Re-run it whenever connections or proxy URLs change.

**F4 · Control Plane**
- The project needs Application Insights before you register anything (step 45 connects it; check **Manage → Project details → Connected resources → AppInsights**). If you connect it later, register the agents again.
- **Operate → Overview → Register asset**: register each data-product MCP endpoint as a custom agent. **Agent URL** = the MCP server URL (as in the F2 table), **Protocol** = HTTP, **Project** = `contoso-thr985`, **Agent name** = the tool's label (`contoso-commercial`, `contoso-loyalty`, `contoso-demand-forecast`, `contoso-supply-chain`), plus a description. Start with the commercial agent (spike S3), then the other three.
- Then run `python foundry/gateway.py`. It finds each registered endpoint's gateway URL in API Management and points the matching connection at it. Foundry sends an MCP tool's calls to the URL stored in its project connection, not to the tool's server URL, so this is what puts the calls behind the gateway. Credentials and redirect URLs stay as they are, so nobody consents again. `--only <label>` limits it to some agents, and `--direct` points them back at Snowflake and Databricks. Then run `python foundry/agents.py --only contoso-orchestrator` (`--only` keeps designs A and B as benchmarked). The commercial connection is shared with design B, so design B goes through the gateway too.
- No API Management subscription key is needed: Control Plane creates the API with `subscriptionRequired: false`, and the gateway forwards the `Authorization` header unchanged (verified 2026-11-03 with a key-pair token through the gateway).
- Verified 2026-11-03 for `contoso-commercial`: Foundry → gateway → Snowflake, and Snowflake still sees the person (`AVA@…`, role `ANALYST_WEST`). The answer is unchanged. Block and Unblock take effect within seconds of Control Plane writing the policy (Unblock: policy at 21:55:59 UTC, first `200` at 21:56:01). The gateway's request metrics lag by about two minutes.
- **Kill switch:** **Operate → Assets** → select the agent → **Update status → Block** (or **Unblock**). Block adds a policy that answers every request with `403 AgentBlocked`. The agent keeps running on its platform, but nothing reaches it through the gateway. Foundry lists every MCP server's tools at the start of each run, so **one blocked agent stops the whole run** with "Access denied … while enumerating tools (HTTP 403)", even for questions that wouldn't have called it. The kill switch fails closed for every agent that uses the blocked one.
- **Before you delete the gateway** on its own, run `python foundry/gateway.py --direct`. Otherwise every connection points at an API Management instance that no longer exists.

**Try it**
- `python foundry/chat.py --as ava`, then `--as ben` and `--as cara`. Before Databricks exists it talks to design B; afterwards to `contoso-orchestrator`. The first run per person and connection prints a consent link: open it in a private window signed in as that person, then press Enter. Foundry asks for one connection at a time, so someone new to the orchestrator gets up to four links in a row. `python foundry/chat.py --as <person> --check` walks through the missing consents without asking a data question, and prints READY once every MCP server lists its tools for that person. Run it for Ava, Ben and Cara before every demo. The first run per person also opens a browser sign-in. It's then cached (encrypted in your Windows profile, like Azure CLI's sign-in; account record in `state/auth/<person>.json`), so later runs, the benchmark and the demo's command-line backup don't prompt. Delete that file to sign in again.
- In the portal, sign in as each persona (one browser profile each) and use the playground.

### If spike S2 fails (OAuth passthrough)
| Symptom | Fallback |
|---|---|
| Snowflake rejects the Entra token | Try `settings.foundry.snowflakeTokenTypeHeader: true`, then re-run `agents.py`. Still failing: Snowflake OAuth — `scripts/40-entra-identity.ps1 -RedirectUri …`, then `run_snowflake.py --only 61`. The client ID and secret come from `SYSTEM$SHOW_OAUTH_CLIENT_SECRETS('OAUTH_FOUNDRY_MCP')` in Snowsight. |
| Foundry: "Cannot pass Microsoft token to untrusted MCP endpoint" on Genie | Databricks OAuth: `python databricks/oauth_fallback.py --redirect-uri <url>`, then update the two Genie connections with the printed values. |

## Verification
- `python snowflake/check_answers.py` and `python databricks/check_answers.py` must both end with `0 failed`.
- **Demo 2 Part B, as Ava:** −9.4% vs forecast (about 1,780 units / $7.9K below forecast); 9 of 12 West stores missed (superstores held); PO-4471 arrived 8 days late at 75% fill, with 10 stores out of stock while it was late. (`check_answers.py` still checks the narrower answer-key figure: 1,648 units / $7,481 lost on PO-4471's SKUs. No single agent can compute it, because it joins supply chain and forecast data.)
- **As Ben:** +12.0%, with no supply issues.
- Verified 2026-10-30 (orchestrator v6): Ava, Ben and Cara get the expected answers, and running them side by side takes about 84 s each.
- Verified 2026-11-04 (orchestrator v11, all four agents through the AI gateway): Ava twice and Ben twice, run side by side, all correct in 67–72 s with about 15K Foundry tokens each. Cara on design B (also through the gateway) matches the Part A numbers.
- **As Cara (Part A):** Central 9,928 / $41,402 · East 11,869 / $49,845 · South 10,388 / $43,039 · West 9,691 / $39,454.
- **Supply-chain follow-up:** POs are filtered by DC region. "Has Northwind done this before?" shows PO-1196 (DC-South) only to Cara.

## Spike S5 — design A vs B
- Runs at the checkpoint (phase 5), before the AI gateway exists: it needs only Snowflake, and both designs call Snowflake directly. Once the commercial connection points at the gateway (step C3), design B goes through the gateway too (same connection) and design A doesn't.
- Run `python foundry/chat.py --as cara --agent contoso-orchestrator-a`, then the same with `-b` (gives consent), then `python foundry/bench.py --runs 20`.
- The CSV and summary land in `state/bench/` and cover accuracy, latency, Foundry tokens, MCP payload size and distinct SQL per question.
- The recorded results (2026-10-25) used designs A and B at v2. On 2026-11-02 design B was republished (v3) so its Snowflake agent call stays synchronous (see "Snowflake agent tools have an async mode" in the [design notes](../docs/README.md#design-notes)). Its answers are unchanged, but the agent's reply has grown to about 76K characters, so one call now takes about 50 s and 23K Foundry tokens. Re-run the benchmark before you quote B's latency or tokens. Design A is still the benchmarked v2.
- Snowflake side, after about 3 hours (ACCOUNT_USAGE lag):

```sql
SELECT warehouse_name, SUM(credits_used) FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE start_time > DATEADD(day, -1, CURRENT_TIMESTAMP()) AND warehouse_name IN ('WH_CONTOSO_MCP_SQL', 'WH_CONTOSO_AGENTS')
GROUP BY 1;
SELECT service_type, SUM(credits_used) FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
WHERE start_time > DATEADD(day, -1, CURRENT_TIMESTAMP()) GROUP BY 1;   -- Cortex AI usage shows as its own service type
```

## Clean up
1. Run `scripts/99-teardown.ps1`. It deletes the resource group (storage, Key Vault, monitoring, Foundry, and the Azure Databricks workspace with its managed resource group), purges the soft-deleted Key Vault and Foundry resource, and deletes the budget. Add `-RemoveEntra` to also delete Ava, Ben, Cara, their groups and the two app registrations.
2. If you created the AI gateway in another resource group, delete it there. To delete only the gateway and keep everything else, run `python foundry/gateway.py --direct` first.
3. The teardown doesn't touch Snowflake. Drop the `CORE`, `COMMERCIAL`, `LOYALTY` and `GOVERNANCE` databases, the integrations and the external volumes, or end the trial account.

## Learn more
- [Architecture and design notes](../docs/README.md): the architecture, a take-home checklist, why the proof of concept is built this way, and the resources from the session
- [Source code](../src/README.md): what each folder contains
- [Contoso Retail data](../src/data-generator/README.md): the data products, the planted story and the expected answers
