# Architecture and design notes

Background for THR985: the architecture behind the demos, where Microsoft Fabric fits, a take-home checklist, the design notes of the proof of concept, and the resources from the session. To build it yourself, follow the [instructions](../instructions/README.md).

## Architecture
Keep one copy of the data on Azure, let every engine bring its own compute, put an agent at each data product, and govern the agents from Microsoft Foundry. Microsoft Entra ID connects people, agents and workloads across all of it.

| Layer | In the proof of concept | Status (November 2026) |
|---|---|---|
| AI control plane | Microsoft Foundry orchestrator agents call one MCP server per data product, with OAuth identity passthrough. Control Plane registers the four data-product agents. Azure API Management is the AI gateway in front of them, and blocks an agent when you need to. | Foundry MCP tool GA; governing MCP tools through an AI gateway in preview; Control Plane mixed GA and preview |
| Agents at the data | Snowflake Cortex Agents (Commercial, Loyalty) behind Snowflake-managed MCP servers. Azure Databricks Genie agents (Demand Forecast, Supply Chain) behind the Genie Agent MCP server. | Snowflake GA; Genie Agent MCP server in public preview |
| Compute: bring your own | Snowflake warehouses read Snowflake's tables. Azure Databricks SQL warehouses read Snowflake's Iceberg tables directly through catalog federation (foreign tables are read-only). Microsoft Fabric can read the same files through OneLake shortcuts (not built here). | GA |
| Data foundation | Azure Data Lake Storage (dfs endpoint) holds one copy of every table as Apache Iceberg. One writer per data product: Snowflake writes core, commercial and loyalty; Azure Databricks writes demand forecast and supply chain. | GA |
| Identity and security | Microsoft Entra ID signs in the people (Ava, Ben and Cara), the apps (Foundry's MCP client and Snowflake External OAuth) and the workloads (the Azure Databricks Access Connector's managed identity and Snowflake's service principal). | GA |

The data products, their tables, the planted story and the expected answers are in the [data generator](../src/data-generator/README.md).

## Where Microsoft Fabric fits
- **Fabric can read this copy.** OneLake shortcuts read the Iceberg tables in place, and Unity Catalog mirroring brings in metadata only: no data is copied, and permissions don't carry over.
- **Why this copy stays in Data Lake Storage.** The teams already run these data products on Snowflake and Azure Databricks, the design needs private networking end to end, and Snowflake to OneLake works over the public network only.
- **Starting fresh?** Fabric gives you this pattern as SaaS, and OneLake is built on Data Lake Storage. The same rule applies: each engine enforces its own policies.

## Take-home checklist
1. One writer per data product; everyone else reads
2. Iceberg on Data Lake Storage, dfs endpoint, one URL per table in code
3. Soft delete and backups (no Fail-safe on external volumes)
4. Require direct reads; alert on query-federation fallback
5. Governed views, never raw foreign tables; policy as code
6. Least-privilege federation connection; secrets in Key Vault
7. Private connectivity per engine before locking storage
8. One MCP endpoint per data product, with an agent behind it
9. Register every agent in Foundry; route MCP through the AI gateway
10. Carry the user's identity end to end; define dates like "last week"

## Design notes
Why the proof of concept is built the way it is, and what was verified while building it.

**Storage and Iceberg**
- **One writer per data product.** Azure RBAC is enforced per container. User-delegation SAS needs Storage Blob Delegator at account scope, and the SAS can't exceed the container role, so each engine writes only its own containers.
- **Iceberg for other engines.** Tables use the `dfs` endpoint and `STORAGE_SERIALIZATION_POLICY = COMPATIBLE`. The default, `OPTIMIZED`, can't be changed after creation. Integers use Iceberg `int` and money uses `DECIMAL(12,2)`.

**Governance**
- **Policies don't travel.** Snowflake row access policies don't apply to Databricks direct reads (catalog federation), and row filters can't be set on foreign tables. Databricks therefore reads Snowflake's sales through governed views filtered by Entra group, and users get no access to the `sf_*` catalogs. (Verified 2026-10-25: Databricks reads `FACT_SALES_DAILY` directly despite its row access policy.)
- **Catalog federation falls back silently.** If Databricks can't use a table's Iceberg metadata, it reads the table over JDBC instead (query federation): same answers, but a Snowflake warehouse runs every read. The federation role needs USAGE on the table's external volume (`10_storage.sql`). `setup_platform.py` stops when a table's provider isn't `iceberg`. Each catalog refresh also probes every object the role can see, so Snowflake logs about 60 harmless "is not a Snowflake iceberg table" errors per database (the `INFORMATION_SCHEMA` views).
- **Workspace access needs an entitlement.** Since September 2026, assigning a group to a workspace grants no entitlements, and the `users` group has none to pass on. Members then get 403 on every workspace API, Genie MCP included, even with the Genie and data grants in place. `setup_account.py` gives the reader groups consumer access (Genie agents and MCP tools; nothing to author). Group membership is enough: people don't need to be added one by one or sign in to the workspace first. (Verified 2026-10-27.)
- **Cortex Search runs as the owner.** Row access on the source isn't applied to the caller, so there is one field-notes search service per region with USAGE per region role. The agent uses `tool_not_accessible: accept`.
- **Search needs subquery-free policies.** A Cortex Search service needs change tracking on its source, and change tracking rejects a row access policy that contains any subquery: a mapping-table lookup with `EXISTS` or `IN`, even inside a memoizable function. So `RAP_REGION` holds its role → region rules as plain `IS_ROLE_IN_SESSION` checks.

**Agents and cost**
- **Agents run as the caller.** They use the caller's default role and warehouse, which `50_users_roles.sql` sets explicitly. Cortex Agent models are pinned, and so is the Foundry model version (`settings.foundry`).
- **Snowflake agent tools have an async mode.** Snowflake's MCP server gives every Cortex Agent tool a `background` option and publishes `ASYNC_AGENT_RUN_STATUS`, `AGENT_RUN_RESULT` and `ASYNC_AGENT_RUN_CANCEL` next to it. These aren't in the CREATE MCP SERVER docs yet; `tools/list` shows them (verified 2026-11-02). A background call returns only a run ID, and `allowed_tools` keeps the other three tools hidden. So the orchestrator and design B are told to call synchronously; before that, one call in a run came back `in_progress`, and the whole agent ran again.
- **Genie answers asynchronously.** Over MCP, `query_space` waits about 16 s and returns a status; the client then calls `poll_response` (about 10 s per call) until the status is COMPLETED. The orchestrator is told to keep polling and to call the three agents in parallel; before that, it gave up after 4 polls and skipped supply chain. Each space has a curated example SQL for the exact question the orchestrator asks, so Genie reuses it: about 30 s per answer and the same numbers every time. Free-form SQL drifted (it averaged fill rate per SKU), and the space's "round to one decimal" rule turned 0.75 into 0.8, so fill rate is reported as a percentage. The supply-chain query always returns rows, with an explicit `none` row per visible DC when no PO was late. Given an empty result, Genie once rewrote the query by itself and matched June–August POs to the promotion week's stockouts.
- **Federation reads metadata on every query.** Each query on a federated Iceberg table first asks Snowflake for the table's current metadata: four statements per table, on cloud services only (no warehouse runs). That adds about 4 s per query on a warm SQL warehouse and 27 s on a cold one, and Genie runs each query twice (the query and a `DESCRIBE`). The first query after the warehouse starts still compiles for 13–19 s, so warming up means running a query on a federated table, not just starting the warehouse.
- **Foundry runs MCP calls one at a time.** The orchestrator asks for the three agents in parallel, but Foundry executes the calls in sequence. Each Genie `query_space` call blocks for about 17–21 s, then the Commercial Analyst agent runs for 26–38 s (including about 8 s of suggested follow-up questions that the orchestrator never uses). Genie keeps working in the background, so both answers are ready when the orchestrator polls. Reasoning effort `low` on the orchestrator brought a run down from 125 s (medium spent about 2.5K reasoning tokens over four turns) with the same answer. Since 2026-11-04 the commercial agent is asked only what the field notes say about the promotion. Its reply shrank from about 74K to 5–14K characters, and Part B takes 65–75 s with about 15K Foundry tokens instead of about 33K. Asking for notes "tagged with promotion PR-…" made the agent search for that literal code, which no note text contains, so the question describes what to look for instead.
- **Cost evidence.** Each consumer gets its own Snowflake warehouse: design A, design B, the Databricks connection (`WH_CONTOSO_FED`: credits there mean query-federation fallback) and the build/default warehouse. All alerts are notify-only.
- **Network.** Only Key Vault has an IP allowlist. Snowflake and Databricks stay public because Foundry's outbound IPs aren't fixed; access is protected by Entra/OAuth/key-pair auth and MFA. Storage lockdown is step 90.

## Items to verify on first run
**Databricks**
- Verified 2026-10-25: catalog federation's SQL form works (`OPTIONS (database, authorized_paths, storage_root)`); Unity Catalog stores `database` and `authorized_paths` as options and `storage_root` as the catalog's storage root.
- Genie `serialized_space` accepted by the API. If not, `setup_genie.py` writes `state/genie_<product>.json` for a manual build.

**Snowflake**
- `DROP ALL ROW ACCESS POLICIES` on a table with none attached is marked `@may-fail`.
- Verified 2026-10-17: Cortex Search services build directly on the Iceberg table.

**Foundry**
- The *Foundry Agent Consumer* role is resolved by name. If it's missing, users keep Foundry User only.
- Model quota comes from your subscription's **quota tier** (check: `az rest --method get --url "https://management.azure.com/subscriptions/<id>/providers/Microsoft.CognitiveServices/quotaTiers?api-version=2025-10-01-preview"`). The default model, gpt-5-mini, is in the Free Tier that a new or Visual Studio subscription can start on; newer models such as gpt-5.4-mini may not be. To use one, request quota at [aka.ms/oai/stuquotarequest](https://aka.ms/oai/stuquotarequest) (priority goes to subscriptions that use their existing quota), change `foundry.model`, `modelVersion` and `deploymentName`, and re-run step 45 and `foundry/agents.py`. Switch before the S5 benchmark, or re-run it.

## Resources from the session
- [Azure Data Lake Storage overview](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-introduction)
- [Azure Databricks: Enable Snowflake catalog federation](https://learn.microsoft.com/en-us/azure/databricks/query-federation/snowflake-catalog-federation)
- [Snowflake: Configure an external volume for Azure](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-external-volume-azure)
- [Snowflake: Snowflake-managed MCP server](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp)
- [Azure Databricks: Genie Agent MCP server](https://learn.microsoft.com/en-us/azure/databricks/agents/mcp-tools/genie-agent) (public preview), and the overview of [Databricks-provided MCPs](https://learn.microsoft.com/en-us/azure/databricks/agents/mcp-tools/built-in-mcp-services)
- [Microsoft Fabric: Use Iceberg tables with OneLake](https://learn.microsoft.com/en-us/fabric/onelake/onelake-iceberg-tables)
- [Microsoft Foundry: Manage existing custom agents in Control Plane](https://learn.microsoft.com/en-us/azure/foundry/control-plane/register-custom-agent)
- [Microsoft Foundry: Govern MCP tools by using an AI gateway](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/governance)
