#!/usr/bin/env python3
"""
Contoso Retail - synthetic data generator for the THR985 demo
("Enterprise Data & AI with Azure, Azure Databricks and Snowflake", Microsoft Ignite 2026).

Deterministic, retail-realistic data organized as data products owned by two platforms:

  snowflake/   Snowflake-managed Iceberg tables on ADLS (Snowflake writes)
    core/             dim_date, dim_store, dim_dc, dim_supplier, dim_product
    commercial/       fact_sales_daily, dim_promotion, bridge_promotion_sku, field_notes
    loyalty/          dim_member (PII), fact_member_weekly
  databricks/  Unity Catalog managed tables on ADLS (Databricks writes)
    demand_forecast/  fact_demand_forecast_weekly
    supply_chain/     fact_inventory_daily, fact_supplier_po

Planted story in the last week of data (the "demo week": Monday..Sunday ending --end-date):
  * "Holiday Kickoff": 25% off Northwind Sparkle sparkling water and Volt Energy drinks in all regions.
  * Northwind Traders' promo allocation PO (PO-4471) to DC-West slips 8 days and arrives ~75% filled,
    so five promo SKUs run out in most West stores mid-week. West superstores carry deeper backroom
    stock and hold out. East beats forecast on the same promo.
  * Field notes (unstructured text) and loyalty visits echo the story.

All names, emails (example.com) and phone numbers (555-01xx) are fictitious.

Usage:
  python generate_contoso_retail.py [--out ./data] [--end-date 2026-11-15] [--weeks 26] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import contoso_reference as ref
import contoso_sim as sim
from contoso_answer_key import build_answer_key, json_default, print_answer_key

LAYOUT = {  # table -> (platform, data product)
    "dim_date": ("snowflake", "core"), "dim_store": ("snowflake", "core"), "dim_dc": ("snowflake", "core"),
    "dim_supplier": ("snowflake", "core"), "dim_product": ("snowflake", "core"),
    "fact_sales_daily": ("snowflake", "commercial"), "dim_promotion": ("snowflake", "commercial"),
    "bridge_promotion_sku": ("snowflake", "commercial"), "field_notes": ("snowflake", "commercial"),
    "dim_member": ("snowflake", "loyalty"), "fact_member_weekly": ("snowflake", "loyalty"),
    "fact_demand_forecast_weekly": ("databricks", "demand_forecast"),
    "fact_inventory_daily": ("databricks", "supply_chain"), "fact_supplier_po": ("databricks", "supply_chain"),
}


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(Path(__file__).with_name("data")))
    ap.add_argument("--end-date", default="2026-11-15", help="last day of data (a Sunday); its week is the demo week")
    ap.add_argument("--weeks", type=int, default=26)
    ap.add_argument("--members", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=42)
    return ap.parse_args()


def build_sales(cal, stores, products, out, disc, pidx, promos):
    d, s, p = np.nonzero(out["sold"] > 0)
    units = out["sold"][d, s, p].astype(np.int32)
    price, cost = products.unit_price.to_numpy()[p], products.unit_cost.to_numpy()[p]
    gross = units * price
    disc_amt = gross * disc[d, s, p]
    net = gross - disc_amt
    promo_ids = np.array(list(promos.promo_id) + [None], dtype=object)  # index -1 -> None
    return pd.DataFrame({
        "date": np.array(cal.days, dtype=object)[d], "store_id": stores.store_id.to_numpy()[s],
        "sku": products.sku.to_numpy()[p], "units_sold": units, "gross_sales": np.round(gross, 2),
        "discount_amount": np.round(disc_amt, 2), "net_sales": np.round(net, 2),
        "cogs": np.round(units * cost, 2), "gross_margin": np.round(net - units * cost, 2),
        "promo_id": promo_ids[pidx[d, s, p].astype(int)],
    })


def build_inventory(cal, stores, products, out):
    D, S, P = out["sold"].shape
    di, si, pi = (a.ravel() for a in np.meshgrid(np.arange(D), np.arange(S), np.arange(P), indexing="ij"))
    return pd.DataFrame({
        "date": np.array(cal.days, dtype=object)[di], "store_id": stores.store_id.to_numpy()[si],
        "sku": products.sku.to_numpy()[pi], "on_hand_units": out["on_hand"].ravel().astype(np.int32),
        "on_order_units": out["on_order"].ravel().astype(np.int32), "received_units": out["received"].ravel().astype(np.int32),
        "stockout_flag": out["stockout"].ravel(), "days_of_supply": np.minimum(out["days_of_supply"].ravel(), 99.0),
    })


def build_forecast(cal, stores, products, lam_plan, pidx, rng):
    Wf, S, P = cal.weeks + 2, len(stores), len(products)
    weekly = lam_plan.reshape(Wf, 7, S, P).sum(axis=1)
    cats = list(pd.unique(products.category))
    bias = rng.lognormal(0, 0.015, (Wf, len(cats)))[:, products.category.map(cats.index).to_numpy()]
    f = weekly * rng.lognormal(0, 0.05, weekly.shape) * bias[:, None, :]
    sd = np.sqrt(f + (0.12 * f) ** 2)
    promo = (pidx.reshape(Wf, 7, S, P) >= 0).any(axis=1)
    wi, si, pi = (a.ravel() for a in np.meshgrid(np.arange(Wf), np.arange(S), np.arange(P), indexing="ij"))
    starts = [cal.start + timedelta(days=7 * i) for i in range(Wf)]
    version = np.array(["v3.4" if ws >= cal.end - timedelta(days=41) else "v3.3" for ws in starts])
    generated = np.array([datetime.combine(ws - timedelta(days=3), time(2, 0)) for ws in starts], dtype="datetime64[us]")
    return pd.DataFrame({
        "forecast_week_start": np.array(starts, dtype=object)[wi], "store_id": stores.store_id.to_numpy()[si],
        "sku": products.sku.to_numpy()[pi], "forecast_units": np.round(f.ravel(), 1),
        "forecast_p10": np.round(np.maximum(0, f - 1.2816 * sd).ravel(), 1), "forecast_p90": np.round((f + 1.2816 * sd).ravel(), 1),
        "promo_flag": promo.ravel(), "model_name": "contoso-demand-gbm", "model_version": version[wi], "generated_at": generated[wi],
    })


def affected_west_stores(cal, stores, out, hk):
    """West stores with 2+ days of stockouts on the delayed promo SKUs during the demo week."""
    demo = slice(7 * (cal.weeks - 1), 7 * cal.weeks)
    days = out["stockout"][demo][:, :, hk["constrained"]].any(axis=2)  # [7, S]
    return days, (days.sum(axis=0) >= 2) & (stores.region.to_numpy() == "West")


def build_loyalty(cal, stores, affected, rng, n):
    S, W = len(stores), cal.weeks
    size = stores.store_format.map(ref.FORMAT_SIZE).to_numpy()
    home = rng.choice(S, n, p=size / size.sum())
    tier = rng.choice(["Gold", "Silver", "Bronze"], n, p=[0.15, 0.35, 0.50])
    first, last = rng.choice(ref.FIRST_NAMES, n), rng.choice(ref.LAST_NAMES, n)
    region = stores.region.to_numpy()[home]
    ids = np.array([f"M{i + 1:06d}" for i in range(n)])
    span = (cal.end - date(2015, 1, 1)).days
    members = pd.DataFrame({
        "member_id": ids, "first_name": first, "last_name": last,
        "email": [f"{a}.{b}{i % 997}@example.com".lower() for i, (a, b) in enumerate(zip(first, last))],
        "phone": [f"+1-{ref.REGION_AREA_CODE[r]}-555-01{int(x):02d}" for r, x in zip(region, rng.integers(0, 100, n))],
        "birth_year": rng.integers(1950, 2007, n), "loyalty_tier": tier,
        "join_date": [date(2015, 1, 1) + timedelta(days=int(x)) for x in rng.integers(0, span, n)],
        "home_store_id": stores.store_id.to_numpy()[home], "home_region": region,
        "marketing_opt_in": rng.random(n) < 0.7,
    })
    rate = pd.Series(tier).map({"Gold": 1.8, "Silver": 1.0, "Bronze": 0.5}).to_numpy()
    basket = pd.Series(tier).map({"Gold": 54.0, "Silver": 41.0, "Bronze": 33.0}).to_numpy()
    bev_share = rng.beta(2, 8, n)
    v_mult, b_mult, r_mult = np.ones((W, n)), np.ones((W, n)), np.ones((W, n))
    hit, east = affected[home], region == "East"
    v_mult[W - 1, hit], b_mult[W - 1, hit], r_mult[W - 1, hit] = 0.82, 0.55, 0.4
    v_mult[W - 1, east], b_mult[W - 1, east] = 1.04, 1.12
    visits = rng.poisson(rate[None, :] * v_mult)
    net = visits * basket[None, :] * rng.lognormal(-0.35 ** 2 / 2, 0.35, (W, n))
    bev = net * bev_share[None, :] * rng.uniform(0.85, 1.15, (W, n)) * b_mult
    red = rng.poisson(0.35 * visits * r_mult)
    w, m = np.nonzero(visits > 0)
    starts = np.array([cal.start + timedelta(days=7 * i) for i in range(W)], dtype=object)
    weekly = pd.DataFrame({
        "week_start_date": starts[w], "member_id": ids[m], "home_store_id": stores.store_id.to_numpy()[home][m],
        "visits": visits[w, m].astype(np.int32), "net_sales": np.round(net[w, m], 2),
        "beverage_sales": np.round(bev[w, m], 2), "promo_redemptions": red[w, m].astype(np.int32),
    })
    return members, weekly


def _fmt(d):
    return f"{d:%b} {d.day}"


def build_field_notes(cal, stores, products, hk, so_days, rng, n_routine=160):
    """Unstructured store/regional notes (Cortex Search corpus), including the planted story."""
    region_of = stores.region.to_numpy()
    subcats = list(products.subcategory.unique())
    cat_of = dict(zip(products.subcategory, products.category))
    items = products.groupby("subcategory").product_name.apply(list).to_dict()
    rows = []
    for _ in range(n_routine):
        d = cal.start + timedelta(days=int(rng.integers(0, len(cal.days))))
        topic, author, store_level, tmpl = ref.ROUTINE_NOTES[int(rng.integers(len(ref.ROUTINE_NOTES)))]
        s, sub = int(rng.integers(len(stores))), subcats[int(rng.integers(len(subcats)))]
        region, cat = region_of[s], cat_of[sub]
        if d >= cal.monday - timedelta(days=3) and (cat == "Beverages" or topic == "Supplier delivery"):
            continue  # keep the planted story's notes unambiguous
        sup = ref.SUPPLIERS[int(rng.integers(len(ref.SUPPLIERS)))][1]
        text = tmpl.format(subcat=sub, category=cat, region=region, aisle=int(rng.integers(1, 18)), k=int(rng.integers(3, 9)),
                           weather=str(rng.choice(ref.WEATHER)), pct=int(rng.integers(5, 21)), event=str(rng.choice(ref.EVENTS)),
                           n=int(rng.integers(2, 5)), shift=str(rng.choice(ref.SHIFTS)), deal=str(rng.choice(ref.DEALS)),
                           item=str(rng.choice(items[sub])), supplier=sup, dc=f"DC-{ref.REGION_CODE[region]}",
                           hours=int(rng.integers(2, 9)))
        ts = datetime.combine(d, time(int(rng.integers(7, 19)), int(rng.integers(0, 60))))
        rows.append(dict(note_ts=ts, region=region, store_id=stores.store_id[s] if store_level else None,
                         author_role=author.format(region=region, category=cat), topic=topic, promo_id=None, note_text=text))

    M, pid, fmt = cal.monday, hk["promo_id"], stores.store_format.to_numpy()
    west = [s for s in np.where(region_of == "West")[0]]
    first = {s: int(np.argmax(so_days[:, s])) for s in west if so_days[:, s].any()}
    by_first = lambda f: sorted((s for s in first if fmt[s] == f), key=lambda s: first[s])
    express, neighborhood = by_first("Express"), by_first("Neighborhood")
    supers = [s for s in west if fmt[s] == "Superstore"]
    supers_txt = ("West superstores held up on deeper backroom inventory; the misses are in Neighborhood and Express stores."
                  if all(so_days[:, s].sum() <= 1 for s in supers)
                  else f"{sum(not so_days[:, s].any() for s in supers)} of 3 West superstores stayed in stock.")
    east_super = next(s for s in range(len(stores)) if region_of[s] == "East" and fmt[s] == "Superstore")

    def note(day, hh, mm, region, s, role, topic, text):
        rows.append(dict(note_ts=datetime.combine(day, time(hh, mm)), region=region,
                         store_id=stores.store_id[s] if s is not None else None, author_role=role, topic=topic,
                         promo_id=pid, note_text=text))

    note(M - timedelta(days=12), 9, 15, "All", None, "Category Manager - Beverages", "Promotion plan",
         f"Holiday Kickoff approved for {_fmt(M)}-{cal.end.day}: 25% off Northwind Sparkle sparkling water and Volt Energy "
         f"drinks (8 SKUs) in all regions. Northwind Traders confirmed allocation at 1.4x baseline on PO-4471 for DC-West. "
         f"Stores should build end-cap displays by {_fmt(M - timedelta(days=1))}.")
    note(M - timedelta(days=3), 16, 40, "West", None, "Supply Planner - West", "Supply risk",
         f"Northwind Traders PO-4471 to DC-West has slipped because of a carrier capacity shortage out of Tacoma. "
         f"Revised ETA {_fmt(M + timedelta(days=4))} with about 75% of the ordered quantity. Five Holiday Kickoff SKUs "
         f"are at risk for West stores from mid-week.")
    if express:
        s = express[0]
        note(M + timedelta(days=first[s]), 13, 5, "West", s, "Store Manager", "Out of stock",
             "Holiday Kickoff sparkling water end cap was empty by noon and Volt Energy is sold out. Customers are asking "
             "for rain checks; two complaints about the weekly ad.")
    if neighborhood:
        s = neighborhood[0]
        note(M + timedelta(days=first[s] + 1), 10, 20, "West", s, "Store Manager", "Out of stock",
             "No promo sparkling water or Volt Energy since yesterday afternoon. DC-West says replenishment is on hold "
             "until the Northwind delivery lands.")
    note(M + timedelta(days=3), 15, 30, "West", None, "Regional Manager - West", "Customer experience",
         f"Approved rain checks for Holiday Kickoff beverage SKUs through {_fmt(cal.end + timedelta(days=7))}. Requesting a "
         f"one-week promo extension for West once the Northwind delivery arrives.")
    note(M + timedelta(days=4), 11, 45, "West", None, "Supply Planner - West", "Supply update",
         f"Northwind Traders delivery received at DC-West (about 75% of PO-4471). Store replenishment for the promo SKUs "
         f"resumes tomorrow. {supers_txt}")
    note(M + timedelta(days=3), 18, 10, "East", east_super, "Store Manager", "Promotion performance",
         "Holiday Kickoff end caps are running well above plan; sparkling water reordered twice this week.")
    note(M + timedelta(days=5), 9, 0, "Central", None, "Regional Manager - Central", "Promotion performance",
         "Holiday Kickoff is tracking close to plan across Central; no supply issues.")

    notes = pd.DataFrame(rows).sort_values("note_ts").reset_index(drop=True)
    notes.insert(0, "note_id", [f"N{i + 1:05d}" for i in range(len(notes))])
    notes["note_ts"] = notes["note_ts"].astype("datetime64[us]")
    notes.insert(2, "note_date", notes["note_ts"].dt.date)
    return notes


def write(df, out_dir, table):
    platform, product = LAYOUT[table]
    path = out_dir / platform / product / f"{table}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow", coerce_timestamps="us", allow_truncated_timestamps=True)
    return dict(table=table, platform=platform, data_product=product, rows=len(df), columns=list(df.columns),
                path=path.relative_to(out_dir).as_posix())


def main():
    args = parse_args()
    out_dir = Path(args.out)
    rng = np.random.default_rng(args.seed)
    cal = sim.make_calendar(date.fromisoformat(args.end_date), args.weeks)

    stores, products = sim.build_stores(rng), sim.build_products(rng)
    base, seas, dow = sim.demand_factors(cal, products, stores, rng)
    promos, bridge, plan_up, real_up, disc, pidx, hk = sim.build_promotions(cal, products, stores, rng)
    season = (seas * dow[:, None])[:, None, :]
    lam_plan = base[None] * season * plan_up
    week_of = np.arange(len(cal.plan_days)) // 7
    store_week = rng.lognormal(0, 0.04, (cal.weeks + 2, len(stores)))
    store_week[cal.weeks - 1] = 1.0  # quiet demo week, so the planted signal isn't drowned by noise
    sku_week = rng.lognormal(0, 0.06, (cal.weeks + 2, len(stores), len(products)))
    lam_real = (base[None] * season * real_up * store_week[week_of][:, :, None] * sku_week[week_of])[:len(cal.days)]
    demand = rng.poisson(lam_real * rng.gamma(10.0, 0.1, lam_real.shape)).astype(np.float64)

    po, fill = sim.build_pos(cal, products, stores, lam_plan, hk, rng)
    for col in ("delivered_qty", "delay_days"):
        po[col] = po[col].astype("Int64")
    out = sim.simulate_inventory(cal, stores, lam_plan, demand, fill)
    so_days, affected = affected_west_stores(cal, stores, out, hk)
    members, member_weekly = build_loyalty(cal, stores, affected, rng, args.members)

    tables = {
        "dim_date": sim.build_dim_date(cal), "dim_store": stores, "dim_dc": sim.build_dcs(),
        "dim_supplier": sim.build_suppliers(), "dim_product": products.drop(columns=["velocity", "popularity"]),
        "fact_sales_daily": build_sales(cal, stores, products, out, disc, pidx, promos),
        "dim_promotion": promos, "bridge_promotion_sku": bridge,
        "field_notes": build_field_notes(cal, stores, products, hk, so_days, rng),
        "dim_member": members, "fact_member_weekly": member_weekly,
        "fact_demand_forecast_weekly": build_forecast(cal, stores, products, lam_plan, pidx, rng),
        "fact_inventory_daily": build_inventory(cal, stores, products, out), "fact_supplier_po": po,
    }
    manifest = dict(generator="generate_contoso_retail.py", seed=args.seed, start_date=str(cal.start), end_date=str(cal.end),
                    demo_week=[str(cal.monday), str(cal.end)], holiday_kickoff_promo=hk["promo_id"],
                    tables=[write(df, out_dir, name) for name, df in tables.items()])
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    key = build_answer_key(tables, cal, hk["promo_id"])
    (out_dir / "answer_key.json").write_text(json.dumps(key, indent=2, default=json_default))
    for t in manifest["tables"]:
        print(f"{t['platform']:<11}{t['data_product']:<17}{t['table']:<29}{t['rows']:>10,}")
    print_answer_key(key)


if __name__ == "__main__":
    main()
