# Source

The code behind the THR985 demos: PowerShell and the Azure CLI for Azure and Microsoft Entra, SQL and Python for Snowflake and Azure Databricks, and Python for Microsoft Foundry. Follow the [step-by-step instructions](../instructions/README.md), and run every command from this folder.

| Folder | What's in it |
|---|---|
| [`config/`](config/settings.example.json) | `settings.example.json`: copy it to `settings.json` (git-ignored) and fill in your tenant, subscription and accounts |
| [`scripts/`](scripts/) | PowerShell 7 steps: sign-in, Azure foundation (storage, Key Vault, monitoring, budget), data upload, Entra identities, Foundry setup, Snowflake's storage consent, the Azure Databricks workspace, optional storage lockdown, teardown |
| [`data-generator/`](data-generator/README.md) | Synthetic, deterministic Contoso Retail data, the planted story and the answer key |
| [`snowflake/`](snowflake/) | SQL steps 00-95 (storage integration and external volumes, Iceberg tables, row access and masking, users and roles, External OAuth, semantic views, Cortex Search, Cortex Agents, MCP servers, checks) and their Python runners |
| [`databricks/`](databricks/) | Platform setup (SQL warehouse, storage credential, Snowflake catalog federation), identities and access, Unity Catalog SQL, Genie agents, checks |
| [`foundry/`](foundry/) | Orchestrator agents, the chat client (the demo's command-line backup), the design A vs B benchmark, and the AI gateway wiring |
| [`python/`](python/) | Shared helpers and `requirements.txt` |

Generated values (`state/`), secrets (`.secrets/`), the virtual environment (`.venv/`), `config/settings.json` and the generated data are git-ignored.
