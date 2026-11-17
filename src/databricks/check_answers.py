#!/usr/bin/env python3
"""Checks the Databricks build against the answer key (state/answer_key.json), as the workspace admin (all regions):
catalog federation really reads Iceberg directly, and forecast vs actual (Snowflake sales read live through the
governed views), stockouts, PO-4471, lost sales and Northwind's history match. Exit code 1 on any failure.

  python databricks/check_answers.py

Per-person row filtering is verified in the demo itself (Genie as Ava / Ben / Cara) - SQL can't impersonate users.
"""
import sys

import dbx

pc = dbx.pc
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def main() -> None:
    key = pc.answer_key()
    if not key:
        sys.exit("state/answer_key.json not found - run scripts/30-upload-landing.ps1 first.")
    v = dbx.variables()
    start, end, promo = v["DEMO_WEEK_START"], v["DEMO_WEEK_END"], v["PROMO_ID"]
    w, wid = dbx.workspace(), dbx.warehouse_id()

    def q(sql: str) -> list[list[str]]:
        return dbx.run_sql(w, sql, wid)[1]

    pc.banner("Catalog federation (war stories B and C)")
    for table in ("sf_core.gold.dim_store", "sf_commercial.gold.fact_sales_daily"):
        info = {r[0]: r[1] for r in q(f"DESCRIBE TABLE EXTENDED {table}") if r and r[0]}
        provider = str(info.get("Provider") or info.get("Type") or "")
        check(f"{table} is read as Iceberg (direct, no Snowflake compute)", "iceberg" in provider.lower(), provider)

    promo_skus = f"(SELECT sku FROM demand_forecast.gold.v_promotion_skus WHERE promo_id = '{promo}')"
    delayed = "(SELECT DISTINCT sku FROM supply_chain.gold.supplier_po WHERE po_number = 'PO-4471')"

    pc.banner("Q1 - Holiday Kickoff vs forecast by region")
    got = {r[0]: r for r in q(f"""
        SELECT region, SUM(forecast_units), SUM(actual_units), (SUM(actual_units) / SUM(forecast_units) - 1) * 100
        FROM demand_forecast.gold.v_forecast_vs_actual
        WHERE week_start_date = DATE'{start}' AND sku IN {promo_skus} GROUP BY region""")}
    for exp in key["q1_promo_performance_by_region"]:
        g = got.get(exp["region"])
        ok = bool(g) and abs(float(g[1]) - exp["forecast_units"]) < 0.06 and int(float(g[2])) == int(exp["actual_units"]) \
            and abs(round(float(g[3]), 1) - exp["variance_pct"]) < 0.05
        check(f"{exp['region']}: {exp['variance_pct']:+.1f}% vs forecast", ok,
              f"forecast {float(g[1]):.1f}, actual {int(float(g[2]))}, {float(g[3]):+.1f}%" if g else "missing")

    pc.banner("Q2 - West stores: promo variance and stockouts on the PO-4471 SKUs")
    var = {r[0]: float(r[1]) for r in q(f"""
        SELECT store_id, (SUM(actual_units) / SUM(forecast_units) - 1) * 100
        FROM demand_forecast.gold.v_forecast_vs_actual
        WHERE week_start_date = DATE'{start}' AND region = 'West' AND sku IN {promo_skus} GROUP BY store_id""")}
    so = {r[0]: (int(r[1]), r[2]) for r in q(f"""
        SELECT store_id, COUNT(DISTINCT snapshot_date), CAST(MIN(snapshot_date) AS STRING)
        FROM supply_chain.gold.inventory_daily
        WHERE snapshot_date BETWEEN DATE'{start}' AND DATE'{end}' AND region = 'West' AND stockout_flag
          AND sku IN {delayed} GROUP BY store_id""")}
    bad = []
    for r in key["q2_west_store_detail"]:
        days, first = so.get(r["store_id"], (0, "NaN"))
        if abs(round(var.get(r["store_id"], 999), 1) - r["variance_pct"]) > 0.05 or days != r["stockout_days_delayed_skus"] \
                or (days and first != r["first_stockout"]):
            bad.append(r["store_id"])
    missed = sorted(s for s, x in var.items() if x <= -5)
    check("12 West stores: variance, stockout days, first stockout", not bad, f"mismatch {bad}" if bad else "all match")
    check(f"{len(key['q2_west_stores_missed_promo_forecast'])} of 12 West stores missed (<= -5%)",
          missed == key["q2_west_stores_missed_promo_forecast"], ", ".join(missed))

    pc.banner("Q3/Q4/Q6 - supply chain")
    lines = q("SELECT po_line, sku, delay_days, fill_rate, status FROM supply_chain.gold.supplier_po "
              "WHERE po_number = 'PO-4471' ORDER BY po_line")
    check("PO-4471: 5 lines, 8 days late, 75% fill",
          len(lines) == 5 and all(int(r[2]) == 8 and abs(float(r[3]) - 0.75) < 0.001 for r in lines),
          f"{len(lines)} lines")
    lost = q(f"""
        WITH gap AS (SELECT v.sku, GREATEST(v.forecast_units - v.actual_units, 0) AS lost_units
                     FROM demand_forecast.gold.v_forecast_vs_actual v
                     WHERE v.week_start_date = DATE'{start}' AND v.region = 'West' AND v.sku IN {delayed})
        SELECT SUM(gap.lost_units), SUM(gap.lost_units * p.unit_price * 0.75)
        FROM gap JOIN sf_core.gold.dim_product p ON p.sku = gap.sku""")[0]
    exp4 = key["q4_west_lost_sales_delayed_skus"]
    check("West lost sales on the delayed SKUs",
          round(float(lost[0])) == exp4["units"] and abs(round(float(lost[1])) - exp4["net_sales_usd"]) <= 1,
          f"{round(float(lost[0]))} units, ${round(float(lost[1])):,} (expected {exp4['units']}, ${exp4['net_sales_usd']:,})")
    late = {r[0] for r in q("SELECT DISTINCT po_number FROM supply_chain.gold.supplier_po "
                            "WHERE supplier_name = 'Northwind Traders' AND status IN ('Late', 'Late - Partial')")}
    expected = {r["po_number"] for r in key["q6_northwind_late_deliveries"]}
    check("Northwind late deliveries (incl. PO-1196 before July 4)", late == expected, f"{len(late)} POs")

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed.")
    if not failed:
        print("Next: finish Foundry (README phase 7) - Genie OAuth connections, python foundry/agents.py, Control Plane.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
