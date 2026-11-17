<a name="start-building"></a>

<p align="center">
<img src="img/banner-ignite-26.png" alt="Microsoft Ignite 2026" width="100%"/>
</p>

# [Microsoft Ignite 2026](https://ignite.microsoft.com)

## 🔥THR985: Enterprise Data & AI with Azure, Azure Databricks and Snowflake

### Session description

How do you build an AI-ready data platform when your estate spans Azure, Snowflake, and Azure Databricks? This session examines a real enterprise architecture using medallion layers, Azure Data Lake Storage, Apache Iceberg, catalog federation, identity, and governed agent access. Learn the interoperability decisions, performance traps, and cost trade-offs that appear when multiple platform engines must operate as one trusted Data and AI ecosystem.

### 🚀 Getting started

#### In a guided session

If you're watching the session, live or on demand:

1. Demo 1: see one copy of the sales data, stored as Apache Iceberg in Azure Data Lake Storage, read by Snowflake and Azure Databricks with their own compute
2. Demo 2: see Ava and Ben ask the same question in the Microsoft Foundry playground. Agents in Snowflake and Azure Databricks answer, each person sees only their own region, and then one agent is blocked from Foundry
3. Afterwards, open the [resources from the session](docs/README.md#resources-from-the-session), or follow the [instructions](instructions/README.md) to build it yourself

#### On your own

If you're learning at your own pace:

1. Clone this repository
2. Check the [prerequisites](instructions/README.md#prerequisites): an Azure subscription where you're Owner, a Microsoft Entra tenant where you're Global Administrator, and a new Snowflake Enterprise trial account on Microsoft Azure East US 2
3. Follow the [step-by-step instructions](instructions/README.md) to build the proof of concept, and read the [architecture and design notes](docs/README.md) for why it's built this way

### 🎯 Learning outcomes

By the end of this session, you will be able to:

- Keep one copy of your data as Apache Iceberg tables in Azure Data Lake Storage, and let Snowflake and Azure Databricks each read it with their own compute through catalog federation
- Put an agent in front of each data product, with Snowflake Cortex Agents and Azure Databricks Genie agents behind MCP servers, and pass each user's Microsoft Entra identity end to end so people see only their own data
- Govern those agents from Microsoft Foundry with Control Plane, an AI gateway and a kill switch, and plan for the policy, performance and cost trade-offs of several engines on one copy

### 💻 Technologies used

- Azure Data Lake Storage and Apache Iceberg
- Snowflake: Cortex Agents, Cortex Analyst semantic views, Cortex Search and Snowflake-managed MCP servers
- Azure Databricks: Unity Catalog, Snowflake catalog federation, Genie agents and the Genie Agent MCP server (preview)
- Microsoft Foundry: Foundry Agent Service, Control Plane and Foundry Models (gpt-5-mini)
- Azure API Management as the AI gateway
- Microsoft Entra ID
- Azure Key Vault and Application Insights

### 📚 Continue your learning

Pick your next step based on your learning style:

| Resource | What you'll get |
|----------|-----------------|
| **[Ignite 2026 Next Steps](https://aka.ms/ignite26-next-steps)** | Additional session repos and materials from Microsoft Ignite 2026 |
| **[Microsoft AI Skills Navigator](https://aka.ms/ignite26-asn)** | Discover AI skills, learning paths, and resources for your next step |
| **[Microsoft Learn](https://aka.ms/ignite26-learn)** | Official documentation and guided learning paths on these topics |
| **[Microsoft Foundry Community](https://aka.ms/MicrosoftFoundryDiscord-Ignite26)** | Connect with other learners and experts in our Discord community |

### 🌟 Microsoft Learn MCP Server

The Microsoft Learn MCP Server gives your AI agent direct access to Microsoft's official documentation — grounded, up-to-date answers about the topics in this session.

**GitHub Copilot CLI** — Install with:

```shell
copilot plugin install microsoftdocs/mcp
```

**VS Code** — One-click install:  
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Microsoft_Learn_MCP-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect/mcp/install?name=microsoft-learn&config=%7B%22type%22%3A%22http%22%2C%22url%22%3A%22https%3A%2F%2Flearn.microsoft.com%2Fapi%2Fmcp%22%7D)

For more information, visit the [Learn MCP Server repo](https://aka.ms/learnmcp).

### 👥 Content owners

<table>
<tr>
    <td align="center"><a href="http://github.com/ehsaneskandariboc">
        <img src="https://github.com/ehsaneskandariboc.png" width="100px;" alt="Ehsan Eskandari"/><br />
        <sub><b>Ehsan Eskandari</b></sub></a><br />
            <a href="https://github.com/ehsaneskandariboc" title="talk">📢</a>
    </td>
</tr></table>

### ⚖️ Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft trademarks or logos is subject to and must follow [Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general). Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.

Any use of third-party trademarks or logos are subject to those third-party's policies.
