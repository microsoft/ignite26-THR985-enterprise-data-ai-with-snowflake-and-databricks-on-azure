#!/usr/bin/env python3
"""Checks the Snowflake build against the answer key (state/answer_key.json) and the governance rules, per persona.

  python snowflake/check_answers.py

Impersonates each persona with USE ROLE + USE SECONDARY ROLES NONE (your admin user holds every role), so it tests
exactly what row access, masking and search grants allow - not what your admin user can see. Exit code 1 on failure.
"""
import re
import sys

import sf

pc = sf.pc
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def as_role(cur, role: str, warehouse: str) -> None:
    cur.execute(f"USE ROLE {role}")
    cur.execute("USE SECONDARY ROLES NONE")
    cur.execute(f"USE WAREHOUSE {warehouse}")


def rows(cur, sql: str) -> list[tuple]:
    cur.execute(sql)
    return cur.fetchall()


def fails(cur, sql: str) -> tuple[bool, str]:
    try:
        cur.execute(sql)
        cur.fetchall()
        return False, "query succeeded"
    except Exception as e:  # noqa: BLE001
        return True, str(e).splitlines()[0][:90]


def main() -> None:
    key = pc.answer_key()
    if not key:
        sys.exit("state/answer_key.json not found - run scripts/30-upload-landing.ps1 first.")
    v = sf.variables()
    promo, start, end, wh = v["PROMO_ID"], v["DEMO_WEEK_START"], v["DEMO_WEEK_END"], v["WAREHOUSE"]
    if not re.fullmatch(r"[A-Z0-9-]+", promo):
        sys.exit(f"Unexpected promo id {promo!r}")
    hk = f"""SELECT region, total_units, total_net_sales FROM SEMANTIC_VIEW(COMMERCIAL.GOLD.SV_COMMERCIAL
             DIMENSIONS sales.region METRICS sales.total_units, sales.total_net_sales
             WHERE sales.promo_id = '{promo}') ORDER BY region"""
    expected_hk = {r["region"]: r for r in key["q1_promo_performance_by_region"]}

    conn = sf.connect()
    cur = conn.cursor()
    try:
        pc.banner("Numbers vs answer key (as Cara / ANALYST_HQ)")
        as_role(cur, "ANALYST_HQ", wh)
        got = {r[0]: r for r in rows(cur, hk)}
        for region, exp in expected_hk.items():
            g = got.get(region)
            ok = bool(g) and int(g[1]) == int(exp["actual_units"]) and abs(float(g[2]) - exp["actual_net_sales"]) < 0.5
            check(f"Holiday Kickoff {region}: units/net sales", ok,
                  f"got {g[1]} / {float(g[2]):.1f}, expected {exp['actual_units']} / {exp['actual_net_sales']}" if g else "missing")

        for label, k, extra in (("all products", "q1b_total_sales_vs_forecast_by_region", ""),
                                ("beverages", "q1c_beverages_vs_forecast_by_region",
                                 "AND s.sku IN (SELECT sku FROM CORE.GOLD.DIM_PRODUCT WHERE category = 'Beverages')")):
            got = {r[0]: r for r in rows(cur, f"""SELECT s.region, SUM(s.units_sold), SUM(s.net_sales)
                    FROM COMMERCIAL.GOLD.FACT_SALES_DAILY s
                    WHERE s.sales_date BETWEEN '{start}' AND '{end}' {extra} GROUP BY s.region""")}
            bad = [r["region"] for r in key[k] if int(got.get(r["region"], (0, -1))[1]) != int(r["actual_units"])]
            check(f"Demo-week units by region, {label}", not bad, f"mismatch: {bad}" if bad else "4 regions match")

        loyalty = rows(cur, f"""WITH weekly AS (SELECT * FROM SEMANTIC_VIEW(LOYALTY.GOLD.SV_LOYALTY
                DIMENSIONS activity.home_region, activity.loyalty_tier, activity.week_start_date
                METRICS activity.total_visits
                WHERE activity.week_start_date BETWEEN '{v['PRIOR_4WK_START']}'::DATE AND '{start}'::DATE))
            SELECT home_region, loyalty_tier,
                   (SUM(IFF(week_start_date = '{start}'::DATE, total_visits, 0))
                    / NULLIF(SUM(IFF(week_start_date < '{start}'::DATE, total_visits, 0)) / 4, 0) - 1) * 100
            FROM weekly GROUP BY 1, 2""")
        exp5 = key["q5_loyalty_visits_change_pct_vs_prior_4wk"]
        bad = [f"{r[0]} {r[1]}" for r in loyalty if abs(round(float(r[2]), 1) - exp5.get(f"{r[0]} {r[1]}", 999)) > 0.05]
        check("Loyalty visits vs prior 4 weeks (12 region x tier cells)", len(loyalty) == 12 and not bad,
              f"West Gold {dict(((r[0], r[1]), round(float(r[2]), 1)) for r in loyalty).get(('West', 'Gold'))}%"
              + (f"; mismatch {bad}" if bad else ""))
        masked = rows(cur, "SELECT first_name, email FROM LOYALTY.GOLD.DIM_MEMBER LIMIT 1")[0]
        check("Cara sees PII masked", masked[0] == "*** masked ***" and str(masked[1]).startswith("***@"), str(masked))

        pc.banner("Row access and search grants")
        as_role(cur, "ANALYST_WEST", wh)
        got = {r[0]: r for r in rows(cur, hk)}
        west = expected_hk["West"]
        check("Ava sees only West Holiday Kickoff", list(got) == ["West"] and int(got["West"][1]) == int(west["actual_units"]),
              f"regions {list(got)}")
        as_role(cur, "ANALYST_EAST", wh)
        regions = {r[0] for r in rows(cur, "SELECT DISTINCT region FROM COMMERCIAL.GOLD.FACT_SALES_DAILY")}
        check("Ben sees only East sales", regions == {"East"}, str(sorted(regions)))
        notes = {r[0] for r in rows(cur, "SELECT DISTINCT region FROM COMMERCIAL.GOLD.FIELD_NOTES")}
        check("Ben sees only East + company-wide notes", notes <= {"East", "All"} and "East" in notes, str(sorted(notes)))
        denied, why = fails(cur, """SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW('COMMERCIAL.GOLD.CSS_FIELD_NOTES_WEST',
                                    '{"query": "PO-4471", "columns": ["note_id"], "limit": 1}')""")
        check("Ben can't query the West field-notes index", denied, why)

        as_role(cur, "FED_READER", "WH_CONTOSO_FED")
        denied, why = fails(cur, "SELECT COUNT(*) FROM COMMERCIAL.GOLD.FIELD_NOTES")
        check("Federation role can't read field notes", denied, why)

        pc.banner("Iceberg storage (war story A)")
        cur.execute("USE SECONDARY ROLES ALL")
        for role, table in (("CORE_OWNER", "CORE.GOLD.DIM_STORE"), ("COMMERCIAL_OWNER", "COMMERCIAL.GOLD.FACT_SALES_DAILY")):
            cur.execute(f"USE ROLE {role}")
            info = rows(cur, f"SELECT SYSTEM$GET_ICEBERG_TABLE_INFORMATION('{table}')")[0][0]
            check(f"{table} metadata on the dfs endpoint", ".dfs.core.windows.net" in info, info[:110])
    finally:
        cur.close()
        conn.close()

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed.")
    if not failed:
        print("Next: the checkpoint (README phase 5) - OAuth connections, python foundry/agents.py, chat as Ava and Ben "
              "(spike S2), the A vs B benchmark (S5); then add the AI gateway from Foundry (S3).")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
