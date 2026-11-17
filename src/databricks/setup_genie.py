#!/usr/bin/env python3
"""Databricks step D4 - one Genie agent per data product, shared with the reader groups, plus their MCP endpoints:

  Demand Forecast  demand_forecast.gold: forecast vs actual (actuals read live from Snowflake), promotion SKUs
  Supply Chain     supply_chain.gold: store inventory / stockouts, supplier purchase orders, promotion SKUs

Genie runs every question as the signed-in person, so the row filters and governed views apply (Ava sees West).
Also grants CAN_USE on the SQL warehouse. Re-running updates the spaces in place.

  python databricks/setup_genie.py
"""
import json
import sys
import time

import dbx
from databricks.sdk.errors import DatabricksError
from databricks.sdk.service import iam

pc = dbx.pc
_seq = [int(time.time() * 1_000_000)]
DEMAND_QUESTION = pc.GENIE_QUESTIONS["demand_forecast"].format(promotion="Holiday Kickoff")
SUPPLY_QUESTION = pc.GENIE_QUESTIONS["supply_chain"].format(promotion="Holiday Kickoff")


def new_id() -> str:
    """Increasing 32-hex ids, so every list in the payload is already sorted by id."""
    _seq[0] += 1
    return f"{_seq[0]:032x}"


def space_payload(tables: list[tuple[str, str]], instructions: str, examples: list[tuple[str, str]],
                  questions: list[str]) -> str:
    """serialized_space, following the structure in the Genie management API docs."""
    return json.dumps({
        "version": 1,
        "config": {"sample_questions": [{"id": new_id(), "question": [q]} for q in questions]},
        "data_sources": {"tables": [{"identifier": t, "description": [d]} for t, d in sorted(tables)]},
        "instructions": {
            "text_instructions": [{"id": new_id(), "content": [instructions]}],
            "example_question_sqls": [{"id": new_id(), "question": [q], "sql": [s]} for q, s in examples],
        },
    })


def spaces(v: dict) -> dict:
    start, end, promo = v["DEMO_WEEK_START"], v["DEMO_WEEK_END"], v["PROMO_ID"]
    common = (f"Weeks run Monday to Sunday. The data ends on {end}: 'last week' means the week starting {start} "
              f"(dates {start} to {end}). Holiday Kickoff is promotion {promo}; get its SKUs from v_promotion_skus. "
              "Regions are West, East, Central and South. The user only sees the regions they are allowed to see - "
              "never say other regions have no data; say they are not visible. Round percentages and units to one "
              "decimal and money to whole dollars.")
    return {
        "demand_forecast": {
            "title": "Contoso Demand Forecast",
            "description": "Forecast vs actual demand by week, store and SKU. Actual sales are read live from Snowflake.",
            "tables": [
                ("demand_forecast.gold.v_forecast_vs_actual", "Forecast vs actual units by week, store and SKU."),
                ("demand_forecast.gold.forecast_weekly", "Weekly forecast by store and SKU, including future weeks."),
                ("demand_forecast.gold.v_promotion_skus", "Promotions and the SKUs they cover."),
            ],
            "instructions": common + " Variance % = (SUM(actual_units) / SUM(forecast_units) - 1) * 100, summed before "
                                     "dividing. A store missed its forecast when variance is -5% or worse.",
            "examples": [
                # The orchestrator asks this exact question (foundry/fdy.py), so Genie runs this SQL: one row per
                # visible region, fast and the same every time.
                (DEMAND_QUESTION,
                 "WITH s AS (SELECT region, store_id, store_format, SUM(forecast_units) AS forecast_units, "
                 "SUM(actual_units) AS actual_units, SUM(GREATEST(forecast_units - actual_units, 0)) AS units_below, "
                 "SUM(GREATEST(forecast_units - actual_units, 0) * actual_net_sales / NULLIF(actual_units, 0)) AS sales_below "
                 "FROM demand_forecast.gold.v_forecast_vs_actual "
                 f"WHERE week_start_date = DATE'{start}' AND sku IN (SELECT sku FROM demand_forecast.gold.v_promotion_skus "
                 f"WHERE promo_id = '{promo}') GROUP BY region, store_id, store_format), "
                 "st AS (SELECT *, (actual_units / forecast_units - 1) * 100 AS variance_pct FROM s) "
                 "SELECT region, ROUND(SUM(forecast_units), 1) AS forecast_units, SUM(actual_units) AS actual_units, "
                 "ROUND((SUM(actual_units) / SUM(forecast_units) - 1) * 100, 1) AS variance_pct, COUNT(*) AS stores, "
                 "COUNT_IF(variance_pct <= -5) AS stores_missed, ARRAY_JOIN(ARRAY_SORT(COLLECT_LIST(CASE WHEN "
                 "variance_pct <= -5 THEN CONCAT(store_id, ' (', ROUND(variance_pct, 1), '%)') END)), ', ') AS stores_that_missed, "
                 "ARRAY_JOIN(ARRAY_SORT(COLLECT_SET(CASE WHEN variance_pct > -5 THEN store_format END)), ', ') AS formats_that_held, "
                 "ROUND(SUM(units_below)) AS units_below_forecast, CAST(ROUND(SUM(sales_below)) AS BIGINT) AS sales_below_forecast_usd "
                 "FROM st GROUP BY region ORDER BY region"),
                ("How did Holiday Kickoff do against forecast last week by region?",
                 "SELECT region, ROUND(SUM(forecast_units), 1) AS forecast_units, SUM(actual_units) AS actual_units, "
                 "ROUND((SUM(actual_units) / SUM(forecast_units) - 1) * 100, 1) AS variance_pct "
                 "FROM demand_forecast.gold.v_forecast_vs_actual "
                 f"WHERE week_start_date = DATE'{start}' AND sku IN (SELECT sku FROM demand_forecast.gold.v_promotion_skus "
                 f"WHERE promo_id = '{promo}') GROUP BY region ORDER BY region"),
                ("Which stores missed the Holiday Kickoff forecast last week?",
                 "SELECT store_id, store_name, store_format, ROUND(SUM(forecast_units), 1) AS forecast_units, "
                 "SUM(actual_units) AS actual_units, ROUND((SUM(actual_units) / SUM(forecast_units) - 1) * 100, 1) AS variance_pct "
                 "FROM demand_forecast.gold.v_forecast_vs_actual "
                 f"WHERE week_start_date = DATE'{start}' AND sku IN (SELECT sku FROM demand_forecast.gold.v_promotion_skus "
                 f"WHERE promo_id = '{promo}') GROUP BY store_id, store_name, store_format "
                 "HAVING (SUM(actual_units) / SUM(forecast_units) - 1) * 100 <= -5 ORDER BY variance_pct"),
            ],
            "questions": [DEMAND_QUESTION,
                          "Which stores missed the Holiday Kickoff forecast last week?",
                          "Which region missed its beverage forecast last week?"],
        },
        "supply_chain": {
            "title": "Contoso Supply Chain",
            "description": "Store inventory, stockouts and supplier purchase orders to the distribution centers.",
            "tables": [
                ("supply_chain.gold.inventory_daily", "End-of-day inventory by store and SKU; stockout_flag = empty shelf."),
                ("supply_chain.gold.supplier_po", "Supplier purchase-order lines to DCs; region = the DC's region."),
                ("supply_chain.gold.v_promotion_skus", "Promotions and the SKUs they cover."),
            ],
            "instructions": common + " Stockout days = number of distinct snapshot_date values with stockout_flag = true. "
                                     "A purchase order is late when status is 'Late' or 'Late - Partial'; delay_days = "
                                     "delivered_date - promised_date; fill_rate = delivered_qty / ordered_qty. "
                                     "Northwind Traders supplies all beverages. Late deliveries for a promotion are POs "
                                     "promised from 14 days before the promotion week to its last day; count stockouts "
                                     "only while such a PO was late. When no PO was late, the answer is a row with "
                                     "po_number 'none': report that no late delivery hit the promotion - never widen the "
                                     "date window or match older POs to the promotion week's stockouts.",
            "examples": [
                # Asked verbatim by the orchestrator: one row per late purchase order, with the stockouts on its SKUs
                # while it was overdue. Always returns rows: an empty result made Genie rewrite the query (wrongly).
                (SUPPLY_QUESTION,
                 "WITH late AS (SELECT po_number, supplier_name, dc_id, dc_name, MIN(promised_date) AS promised_date, "
                 "MAX(delivered_date) AS delivered_date, MAX(delay_days) AS delay_days, ROUND(AVG(fill_rate) * 100, 1) AS fill_rate_pct, "
                 "MAX(reason_code) AS reason_code, COUNT(*) AS po_lines, COLLECT_SET(sku) AS skus "
                 "FROM supply_chain.gold.supplier_po WHERE status IN ('Late', 'Late - Partial') "
                 f"AND sku IN (SELECT sku FROM supply_chain.gold.v_promotion_skus WHERE promo_id = '{promo}') "
                 f"AND promised_date BETWEEN date_sub(DATE'{start}', 14) AND DATE'{end}' "
                 "GROUP BY po_number, supplier_name, dc_id, dc_name), "
                 "impact AS (SELECT l.po_number, l.supplier_name, l.dc_name, l.promised_date, l.delivered_date, l.delay_days, "
                 "l.fill_rate_pct, l.reason_code, l.po_lines, COUNT(DISTINCT i.store_id) AS stores_out_while_late, "
                 "COUNT(DISTINCT i.store_id, i.snapshot_date) AS store_days_out_while_late "
                 "FROM late l LEFT JOIN supply_chain.gold.inventory_daily i ON i.dc_id = l.dc_id "
                 "AND array_contains(l.skus, i.sku) AND i.stockout_flag "
                 f"AND i.snapshot_date BETWEEN GREATEST(l.promised_date, DATE'{start}') AND LEAST(l.delivered_date, DATE'{end}') "
                 "GROUP BY l.po_number, l.supplier_name, l.dc_name, l.promised_date, l.delivered_date, l.delay_days, "
                 "l.fill_rate_pct, l.reason_code, l.po_lines) "
                 "SELECT * FROM impact UNION ALL "
                 "SELECT 'none', CAST(NULL AS STRING), dc_name, CAST(NULL AS DATE), CAST(NULL AS DATE), 0, "
                 "CAST(NULL AS DOUBLE), 'no late delivery for this promotion', 0, 0, 0 "
                 "FROM (SELECT DISTINCT dc_name FROM supply_chain.gold.supplier_po) "
                 "WHERE NOT EXISTS (SELECT 1 FROM impact) ORDER BY delay_days DESC"),
                ("Were there stockouts on Holiday Kickoff products last week, by store?",
                 "SELECT store_id, store_name, store_format, COUNT(DISTINCT snapshot_date) AS stockout_days, "
                 "MIN(snapshot_date) AS first_stockout FROM supply_chain.gold.inventory_daily "
                 f"WHERE snapshot_date BETWEEN DATE'{start}' AND DATE'{end}' AND stockout_flag "
                 f"AND sku IN (SELECT sku FROM supply_chain.gold.v_promotion_skus WHERE promo_id = '{promo}') "
                 "GROUP BY store_id, store_name, store_format ORDER BY stockout_days DESC"),
                ("Which supplier deliveries to my DC were late around the promotion?",
                 "SELECT po_number, supplier_name, dc_name, MIN(promised_date) AS promised_date, "
                 "MAX(delivered_date) AS delivered_date, MAX(delay_days) AS delay_days, ROUND(AVG(fill_rate) * 100, 1) AS fill_rate_pct, "
                 "MAX(reason_code) AS reason_code, COUNT(*) AS lines FROM supply_chain.gold.supplier_po "
                 f"WHERE status IN ('Late', 'Late - Partial') AND promised_date BETWEEN date_sub(DATE'{start}', 14) "
                 f"AND DATE'{end}' GROUP BY po_number, supplier_name, dc_name ORDER BY delay_days DESC"),
            ],
            "questions": [SUPPLY_QUESTION,
                          "Were there stockouts on Holiday Kickoff products in my region last week?",
                          "Which supplier deliveries were late for my DC around the promotion?",
                          "Has Northwind Traders delivered late before?"],
        },
    }


def share(w, object_type: str, object_id: str, groups: list[str], level: iam.PermissionLevel) -> None:
    acl = [iam.AccessControlRequest(group_name=g, permission_level=level) for g in groups]
    try:
        w.permissions.update(request_object_type=object_type, request_object_id=object_id, access_control_list=acl)
        print(f"    {level.value} on {object_type}/{object_id} for {', '.join(groups)}")
    except DatabricksError as e:
        print(f"    WARNING: could not set {level.value} on {object_type}/{object_id}: {str(e).splitlines()[0][:160]}\n"
              f"    -> share it with {', '.join(groups)} from the UI (Share button).")


def ensure_managed_mcp(w) -> None:
    """The Genie MCP endpoints need the Managed MCP Servers preview (workspace setting managed_mcp_servers)."""
    try:
        from databricks.sdk.service import settingsv2
        api = w.workspace_settings_v2
        current = api.get_public_workspace_setting(name="managed_mcp_servers").effective_boolean_val
        if current and current.value:
            print("    Managed MCP Servers preview: on")
            return
        api.patch_public_workspace_setting(name="managed_mcp_servers", setting=settingsv2.Setting(
            name="managed_mcp_servers", boolean_val=settingsv2.BooleanMessage(value=True)))
        print("    Managed MCP Servers preview: turned on (takes effect within a minute)")
    except Exception as e:  # noqa: BLE001
        print(f"    WARNING: couldn't turn on the Managed MCP Servers preview ({str(e).splitlines()[0][:120]}).\n"
              "    Turn it on in the workspace: your user name (top right) > Previews > Managed MCP Servers.")


def check_mcp(w, url: str) -> tuple[bool, str]:
    """Calls the Genie MCP endpoint like Foundry will (initialize, then tools/list). Returns (ok, tool names or error)."""
    import requests

    def call(method: str, params: dict, rid: int, session: str | None):
        headers = {**w.config.authenticate(), "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if session:
            headers["Mcp-Session-Id"] = session
        r = requests.post(url, headers=headers, timeout=60,
                          json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        if r.status_code >= 400:
            return r, {"error": {"message": f"HTTP {r.status_code}: {r.text[:200]}"}}
        if r.headers.get("content-type", "").startswith("text/event-stream"):
            data = [ln[5:].strip() for ln in r.text.splitlines() if ln.startswith("data:")]
            return r, json.loads(data[-1]) if data else {}
        return r, r.json()

    try:
        r, init = call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "contoso-setup", "version": "1"}}, 1, None)
        if init.get("error"):
            return False, init["error"].get("message", str(init["error"]))
        _, tools = call("tools/list", {}, 2, r.headers.get("Mcp-Session-Id"))
        if tools.get("error"):
            return False, tools["error"].get("message", str(tools["error"]))
        return True, ", ".join(t.get("name", "?") for t in tools.get("result", {}).get("tools", []))
    except Exception as e:  # noqa: BLE001
        return False, str(e).splitlines()[0][:200]


def main() -> None:
    st = pc.state()
    if not st.get("databricksGroups"):
        sys.exit("Run python databricks/setup_account.py first.")
    groups = [g for k, g in st["databricksGroups"].items()]
    w, wid, v = dbx.workspace(), dbx.warehouse_id(), dbx.variables()

    pc.banner("SQL warehouse access for the reader groups")
    share(w, "warehouses", wid, groups, iam.PermissionLevel.CAN_USE)

    pc.banner("Genie agents")
    existing = {s.title: s.space_id for s in (w.genie.list_spaces().spaces or [])}
    out = {}
    for product, spec in spaces(v).items():
        payload = space_payload(spec["tables"], spec["instructions"], spec["examples"], spec["questions"])
        try:
            if spec["title"] in existing:
                space_id = existing[spec["title"]]
                w.genie.update_space(space_id, serialized_space=payload, title=spec["title"],
                                     description=spec["description"], warehouse_id=wid)
                print(f"    updated '{spec['title']}' ({space_id})")
            else:
                space_id = w.genie.create_space(warehouse_id=wid, serialized_space=payload, title=spec["title"],
                                                description=spec["description"]).space_id
                print(f"    created '{spec['title']}' ({space_id})")
        except DatabricksError as e:
            dump = pc.ROOT / "state" / f"genie_{product}.json"
            dump.write_text(json.dumps({**spec, "serialized_space": json.loads(payload)}, indent=2), encoding="utf-8")
            sys.exit(f"Genie API rejected '{spec['title']}': {e}\nCreate it in the UI from {dump} "
                     "(tables, instructions, example SQL, sample questions), then re-run to share it.")
        share(w, "genie", space_id, groups, iam.PermissionLevel.CAN_RUN)
        out[product] = {"title": spec["title"], "spaceId": space_id,
                        "mcpUrl": f"{st['databricksWorkspaceUrl']}/api/2.0/mcp/genie/{space_id}"}
    pc.update_state({"databricksGenie": out})

    pc.banner("Genie MCP endpoints (for Foundry)")
    ensure_managed_mcp(w)
    for attempt in range(1, 7):
        results = {product: check_mcp(w, g["mcpUrl"]) for product, g in out.items()}
        if all(ok for ok, _ in results.values()) or attempt == 6:
            break
        time.sleep(20)  # a newly enabled preview takes a little while to reach the endpoints
    problems = []
    for product, g in out.items():
        ok, detail = results[product]
        print(f"    {g['title']}: {g['mcpUrl']}\n      {'answers - tools: ' + detail if ok else 'NOT READY: ' + detail}")
        if not ok:
            problems.append(detail)
    if problems:
        if any("not enabled" in p.lower() for p in problems):
            sys.exit("\nTurn on the Managed MCP Servers preview (workspace admin): in the workspace, select your user "
                     "name (top right) > Previews > Managed MCP Servers > On. Then re-run this script; it checks again.")
        sys.exit("\nThe Genie MCP endpoints don't answer yet (see above). Fix that, then re-run this script.")
    print("\nNext: python databricks/check_answers.py, then finish Foundry (README phase 7): the two Genie OAuth "
          "connections, python foundry/agents.py, Control Plane.")


if __name__ == "__main__":
    main()
