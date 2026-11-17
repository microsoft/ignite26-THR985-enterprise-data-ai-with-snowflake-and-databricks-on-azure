"""Foundry helpers: project client, MCP tool definitions (one per data-product MCP server), and the three agents."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import poc_common as pc  # noqa: E402

ORCHESTRATOR = "contoso-orchestrator"      # Demo 2 Part B: four data-product agents (needs Databricks)
DESIGN_A = "contoso-orchestrator-a"        # Part A / S5: semantic view + read-only SQL (commercial only)
DESIGN_B = "contoso-orchestrator-b"        # Part A / S5: the Commercial Analyst agent (commercial only)


class NotReady(Exception):
    """An agent's MCP server or Foundry connection doesn't exist yet - build that part first."""


def endpoint() -> str:
    ep = pc.state().get("foundryProjectEndpoint")
    if not ep:
        sys.exit("No Foundry project in state - run scripts/45-foundry.ps1 first.")
    pc.assert_personal_tenant()
    return ep


def snowflake_mcp_url(database: str, server: str) -> str:
    account = (pc.settings()["snowflake"].get("account") or "").lower().replace("_", "-")
    if not account:
        sys.exit("Set snowflake.account in config/settings.json.")
    return f"https://{account}.snowflakecomputing.com/api/v2/databases/{database}/schemas/GOLD/mcp-servers/{server}"


def tool_specs() -> dict:
    """Genie URLs stay empty until databricks/setup_genie.py has run, so the Snowflake-only agents can be built first."""
    genie = pc.state().get("databricksGenie") or {}
    demand, supply = genie.get("demand_forecast") or {}, genie.get("supply_chain") or {}
    return {
        "commercialAgent": {
            "label": "contoso-commercial", "url": snowflake_mcp_url("COMMERCIAL", "MCP_COMMERCIAL_AGENT"),
            "allowed": ["commercial-analyst"], "snowflake": True,
            "description": "Commercial data product (Snowflake Cortex Agent): sales, promotions, store field notes."},
        "commercialSql": {
            "label": "contoso-commercial-sql", "url": snowflake_mcp_url("COMMERCIAL", "MCP_COMMERCIAL_SQL"),
            "allowed": ["commercial-semantic-view", "run-sql"], "snowflake": True,
            "description": "Commercial data product (Snowflake): semantic view to SQL, and read-only SQL."},
        "loyaltyAgent": {
            "label": "contoso-loyalty", "url": snowflake_mcp_url("LOYALTY", "MCP_LOYALTY_AGENT"),
            "allowed": ["loyalty-analyst"], "snowflake": True,
            "description": "Loyalty data product (Snowflake Cortex Agent): member visits, tiers and spend."},
        "demandForecast": {
            "label": "contoso-demand-forecast", "url": demand.get("mcpUrl"), "allowed": None, "snowflake": False,
            "description": "Demand forecast data product (Databricks Genie): forecast vs actual by week, store, SKU."},
        "supplyChain": {
            "label": "contoso-supply-chain", "url": supply.get("mcpUrl"), "allowed": None, "snowflake": False,
            "description": "Supply chain data product (Databricks Genie): stockouts and supplier purchase orders."},
    }


def mcp_tool(project_client, key: str):
    """MCP tool bound to its OAuth connection. Raises NotReady if the server or the connection doesn't exist yet.
    Foundry sends the calls to the connection's target URL (foundry/gateway.py points it at the AI gateway), so the
    tool shows that URL too."""
    from azure.ai.projects.models import MCPTool
    from azure.core.exceptions import ResourceNotFoundError
    f = pc.settings()["foundry"]
    spec = tool_specs()[key]
    if not spec["url"]:
        raise NotReady(f"no Genie space for {spec['label']} yet (python databricks/setup_genie.py)")
    conn_name = f["connections"][key]
    try:
        conn = project_client.connections.get(conn_name)
    except ResourceNotFoundError:
        raise NotReady(f"Foundry connection '{conn_name}' doesn't exist yet (README step F2)") from None
    url = conn.target or spec["url"]
    headers = {"X-Snowflake-Authorization-Token-Type": "OAUTH"} \
        if spec["snowflake"] and f.get("snowflakeTokenTypeHeader") else None
    return MCPTool(server_label=spec["label"], server_url=url, server_description=spec["description"],
                   allowed_tools=spec["allowed"], require_approval="never", project_connection_id=conn.id,
                   headers=headers)


def default_agent() -> str:
    """The Part B orchestrator once Databricks is built; design B (Snowflake only) at the checkpoint before that."""
    return ORCHESTRATOR if pc.state().get("databricksGenie") else DESIGN_B


FOUNDRY_SCOPE = "https://ai.azure.com/.default"


def persona_credential(alias: str):
    """Ava/Ben/Cara sign in in a browser the first time. The sign-in is then cached (encrypted in your Windows profile,
    like Azure CLI's) with its account record in state/auth/<alias>.json, so later runs - and the demo's command-line
    backup - don't prompt. Delete that file to sign in again. 'me' uses your Azure CLI login."""
    from azure.identity import (AuthenticationRecord, AuthenticationRequiredError, AzureCliCredential,
                                InteractiveBrowserCredential, TokenCachePersistenceOptions)
    if alias == "me":
        return AzureCliCredential()
    st = pc.state()
    user = (st.get("entraUsers") or {}).get(alias)
    if not user:
        sys.exit(f"Unknown persona '{alias}' - run scripts/40-entra-identity.ps1 first.")
    path = pc.ROOT / "state" / "auth" / f"{alias}.json"
    record = AuthenticationRecord.deserialize(path.read_text(encoding="utf-8")) if path.exists() else None
    cred = InteractiveBrowserCredential(
        tenant_id=st["tenantId"], login_hint=user["upn"], authentication_record=record,
        cache_persistence_options=TokenCachePersistenceOptions(name=f"contoso-thr985-{alias}"),
        disable_automatic_authentication=True)  # never a surprise browser window mid-run
    if record is not None:
        try:
            cred.get_token(FOUNDRY_SCOPE)
            return cred
        except AuthenticationRequiredError:
            pass
    print(f"Sign in as {user['upn']} in the browser window that opens (once; the sign-in is then cached).")
    record = cred.authenticate(scopes=[FOUNDRY_SCOPE])
    if record.username.lower() != user["upn"].lower():
        sys.exit(f"Signed in as {record.username}, not {user['upn']}. Run again and pick {alias}'s account.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.serialize(), encoding="utf-8")
    return cred


def ask(openai_client, question: str, on_consent=None) -> dict:
    """One question to the agent bound to openai_client. Handles OAuth consent (first use per person and tool) and
    returns the answer, latency of the final call, Foundry token usage, every MCP call with its payload size, any
    tool-listing errors, and the raw response.

    Foundry raises one OAuth consent request per response (a person who never used some of the MCP connections
    needs several), and a response continued with previous_response_id after a consent never asks for the next
    one: those servers just list no tools. So after each consent the question starts over as a fresh response."""
    import time
    for _ in range(6):  # at most one consent per MCP connection, plus the real run
        t0 = time.perf_counter()
        resp = openai_client.responses.create(input=question)
        consents = [i for i in resp.output if getattr(i, "type", "") == "oauth_consent_request"]
        if not consents:
            break
        if on_consent is None:
            raise RuntimeError("OAuth consent needed - run foundry/chat.py once as this person first.")
        on_consent([getattr(i, "consent_link", "?") for i in consents])
    else:
        raise RuntimeError("Foundry still asks for OAuth consent after 6 rounds - check the connections (README F2).")
    latency = time.perf_counter() - t0
    list_errors = []
    for i in resp.output:
        if getattr(i, "type", "") != "mcp_list_tools":
            continue
        if getattr(i, "error", None):
            list_errors.append(f"{getattr(i, 'server_label', '?')}: {i.error}")
        elif not getattr(i, "tools", None):
            list_errors.append(f"{getattr(i, 'server_label', '?')}: no tools (no consent yet, or the server refused "
                               "this person's token)")
    calls = []
    for item in resp.output:
        if getattr(item, "type", "") == "mcp_call":
            out = getattr(item, "output", None) or ""
            calls.append({"server": getattr(item, "server_label", "?"), "tool": getattr(item, "name", "?"),
                          "arguments": getattr(item, "arguments", "") or "", "output": out,
                          "error": getattr(item, "error", None)})
    usage = getattr(resp, "usage", None)
    return {"answer": resp.output_text or "", "latency_s": latency, "calls": calls,
            "input_tokens": getattr(usage, "input_tokens", None), "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None), "response_id": resp.id,
            "list_errors": list_errors, "raw": resp}


def agent_definitions(v: dict) -> dict:
    week = f"{v['DEMO_WEEK_START']} to {v['DEMO_WEEK_END']}"
    demand_q = pc.GENIE_QUESTIONS["demand_forecast"].format(promotion="<promotion>")
    supply_q = pc.GENIE_QUESTIONS["supply_chain"].format(promotion="<promotion>")
    rules = (f"The data ends on {v['DEMO_WEEK_END']}: 'last week' means {week}. Holiday Kickoff is promotion "
             f"{v['PROMO_ID']}. Never invent numbers. Every tool answers only with data the signed-in person may see, "
             "so 'my region' means whatever the tools return: never ask which region. If a region or tool is not "
             "available, say so instead of guessing. Never ask the user a clarifying question: choose the most "
             "reasonable reading, say which one you used, and answer.")
    # Snowflake's MCP server gives every agent tool a 'background' option: such a call returns only a run_id, and the
    # status and result tools that collect it are left out of allowed_tools. So the Snowflake agents stay synchronous.
    sync = ("Call the Snowflake agent tools without their background option, so each one answers in the same call; "
            "if one still returns status in_progress with a run_id, ask it the same question once more without "
            "background. ")
    return {
        ORCHESTRATOR: {
            "tools": ["commercialAgent", "loyaltyAgent", "demandForecast", "supplyChain"],
            "reasoning": "low",  # medium spent ~2.5K reasoning tokens over 4 turns; the calls and questions are fixed
            "description": "Contoso retail assistant over four data-product agents (Snowflake and Databricks).",
            "instructions": (
                "You are Contoso's retail performance assistant. You coordinate four data-product agents: "
                "contoso-demand-forecast (Databricks: forecast vs actual by region and store), contoso-supply-chain "
                "(Databricks: stockouts and supplier purchase orders), contoso-commercial (Snowflake: sales, "
                "promotions, store field notes) and contoso-loyalty (Snowflake: loyalty member visits by tier). For a "
                "'how did <promotion> do, and why' question, start these three calls at the same time, in parallel, "
                f"each with exactly this question: contoso-demand-forecast: '{demand_q}'; contoso-supply-chain: "
                f"'{supply_q}'; contoso-commercial: 'What do my stores' field notes say went right or wrong with "
                "<promotion>: displays, stock-outs, deliveries, rain checks, customer feedback? Leave out notes that "
                "aren't about <promotion>. At most five short bullets, each with its note ID (like N00154).'. Call "
                "contoso-loyalty only when the user asks about loyalty members, tiers or customers. " + sync +
                "The two Databricks agents answer asynchronously: while a result's status is not COMPLETED, call that "
                "agent's poll_response tool with the same conversation_id and message_id, again and again, until the "
                "status is COMPLETED or FAILED; when both are pending, poll both in the same step. Each poll waits "
                "about 10 seconds and an answer usually takes 1 to 3 polls; after 8 polls, report that answer as "
                "missing. A pending answer is not a failure: never skip an agent, and never answer while a result is "
                "still pending. Ask each agent its question once. If an agent asks you a question, don't pass it to "
                "the user: answer it with the most reasonable choice and continue. If an agent fails, give the rest of "
                "the answer and say what is missing. Answer with one headline sentence with the key numbers, then at "
                "most four bullets of causes citing PO numbers, store IDs and note IDs; say which store formats held "
                "up when the data shows it. Explain only the regions in the demand-forecast result: leave out facts "
                "about other regions, their DCs and their POs (chain-wide notes can mention them), and notes that "
                "aren't about the promotion. Keep each number's meaning as the agent gives it ('below forecast' is "
                "not 'lost'), round money to whole dollars, and don't offer follow-ups. " + rules)},
        DESIGN_A: {
            "tools": ["commercialSql"],
            "description": "Design A: the orchestrator writes the query path itself - semantic view to SQL, then run it.",
            "instructions": (
                "Answer questions about Contoso sales and promotions. First call commercial-semantic-view with the "
                "user's question to get SQL; then run exactly that SQL with run-sql (never write or change SQL "
                "yourself). Answer with a short table and one sentence. " + rules)},
        DESIGN_B: {
            "tools": ["commercialAgent"],
            "description": "Design B: the orchestrator delegates to the Snowflake Commercial Analyst agent.",
            "instructions": (
                "Answer questions about Contoso sales and promotions by asking the commercial-analyst tool the "
                "user's question as is. " + sync + "Answer with a short table and one sentence. " + rules)},
    }
