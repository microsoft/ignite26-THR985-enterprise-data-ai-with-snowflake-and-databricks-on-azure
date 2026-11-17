"""Expected answers for the demo questions, computed from the published tables (not simulation internals)."""
from __future__ import annotations

import pandas as pd


def json_default(o):
    if hasattr(o, "item"):
        return o.item()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


def _perf(sales_w, fc_w, skus, stores, by):
    reg = stores.set_index("store_id")[["region", "store_name", "store_format"]]
    a = sales_w[sales_w.sku.isin(skus)].join(reg, on="store_id").groupby(by).agg(
        actual_units=("units_sold", "sum"), actual_net_sales=("net_sales", "sum"))
    f = fc_w[fc_w.sku.isin(skus)].join(reg, on="store_id").groupby(by).agg(forecast_units=("forecast_units", "sum"))
    df = f.join(a).fillna(0.0)
    df["variance_pct"] = (df.actual_units / df.forecast_units - 1) * 100
    return df


def build_answer_key(t, cal, hk_promo_id):
    sales, fc, inv, po = t["fact_sales_daily"], t["fact_demand_forecast_weekly"], t["fact_inventory_daily"], t["fact_supplier_po"]
    stores, products, bridge = t["dim_store"], t["dim_product"], t["bridge_promotion_sku"]
    M, E = cal.monday, cal.end
    s_w = sales[(sales.date >= M) & (sales.date <= E)]
    f_w = fc[fc.forecast_week_start == M]
    hk_skus = bridge.loc[bridge.promo_id == hk_promo_id, "sku"].tolist()
    po_hk = po[po.po_number == "PO-4471"]
    delayed = po_hk.sku.tolist()
    prod = products.set_index("sku")

    region_promo = _perf(s_w, f_w, hk_skus, stores, "region")
    region_total = _perf(s_w, f_w, products.sku.tolist(), stores, "region")
    region_bev = _perf(s_w, f_w, products.loc[products.category == "Beverages", "sku"].tolist(), stores, "region")

    inv_w = inv[(inv.date >= M) & (inv.date <= E) & inv.sku.isin(delayed) & inv.stockout_flag]
    so_days = inv_w.groupby("store_id").date.nunique()
    first_so = inv_w.groupby("store_id").date.min()
    st = _perf(s_w, f_w, hk_skus, stores, "store_id")
    st_delayed = _perf(s_w, f_w, delayed, stores, "store_id")
    meta = stores.set_index("store_id")[["store_name", "store_format", "region"]]
    west = meta[meta.region == "West"].join(st[["forecast_units", "actual_units", "variance_pct"]]) \
        .join(st_delayed[["variance_pct"]].rename(columns={"variance_pct": "delayed_skus_variance_pct"}))
    west["stockout_days_delayed_skus"] = so_days.reindex(west.index).fillna(0).astype(int)
    west["first_stockout"] = first_so.reindex(west.index)
    missed = west[west.variance_pct <= -5]

    # Lost sales on the delayed SKUs in West: forecast minus actual, floored at zero, at the promo price.
    region_of = stores.set_index("store_id").region
    fw = f_w[f_w.sku.isin(delayed)]
    fw = fw[fw.store_id.map(region_of) == "West"].set_index(["store_id", "sku"]).forecast_units
    aw = s_w[s_w.sku.isin(delayed)].groupby(["store_id", "sku"]).units_sold.sum()
    gap = (fw - aw.reindex(fw.index).fillna(0)).clip(lower=0)
    skus = gap.index.get_level_values("sku")
    promo_price = prod.unit_price * 0.75
    lost_sales = float((gap.values * promo_price.reindex(skus).values).sum())
    lost_margin = float((gap.values * (promo_price - prod.unit_cost).reindex(skus).values).sum())

    # Loyalty: visits in the demo week vs the prior 4-week average, by region and tier.
    mw = t["fact_member_weekly"].merge(t["dim_member"][["member_id", "loyalty_tier", "home_region"]], on="member_id")
    v = mw.groupby(["home_region", "loyalty_tier", "week_start_date"]).visits.sum().unstack("week_start_date")
    weeks = sorted(v.columns)
    loyalty = ((v[weeks[-1]] / v[weeks[-5:-1]].mean(axis=1) - 1) * 100).round(1)

    nw = po[(po.supplier_id == "SUP01") & po.status.isin(["Late", "Late - Partial"])]
    northwind_late = nw.groupby(["po_number", "dc_id", "promised_date", "delivered_date", "delay_days", "reason_code"]) \
        .agg(lines=("sku", "count"), avg_fill=("fill_rate", "mean")).reset_index()

    return {
        "demo_week": [str(M), str(E)], "promo_id": hk_promo_id,
        "promo_skus": [f"{s} {prod.product_name[s]}" for s in hk_skus],
        "delayed_skus_po_4471": [f"{s} {prod.product_name[s]}" for s in delayed],
        "q1_promo_performance_by_region": region_promo.round(1).reset_index().to_dict("records"),
        "q1b_total_sales_vs_forecast_by_region": region_total.round(1).reset_index().to_dict("records"),
        "q1c_beverages_vs_forecast_by_region": region_bev.round(1).reset_index().to_dict("records"),
        "q2_west_store_detail": west.round(1).reset_index().to_dict("records"),
        "q2_west_stores_missed_promo_forecast": missed.index.tolist(),
        "q3_po_4471": po_hk[["po_line", "sku", "promised_date", "delivered_date", "ordered_qty", "delivered_qty",
                             "delay_days", "fill_rate", "status", "reason_code"]].to_dict("records"),
        "q4_west_lost_sales_delayed_skus": {"units": round(float(gap.sum())), "net_sales_usd": round(lost_sales),
                                            "gross_margin_usd": round(lost_margin)},
        "q5_loyalty_visits_change_pct_vs_prior_4wk": {f"{r} {tier}": val for (r, tier), val in loyalty.items()},
        "q6_northwind_late_deliveries": northwind_late.to_dict("records"),
    }


def print_answer_key(k):
    print(f"\nDemo week {k['demo_week'][0]}..{k['demo_week'][1]}  promo {k['promo_id']}")
    print("Q1  Holiday Kickoff vs forecast by region:")
    for r in k["q1_promo_performance_by_region"]:
        print(f"    {r['region']:<8} forecast {r['forecast_units']:>8.0f}  actual {r['actual_units']:>8.0f}  {r['variance_pct']:+.1f}%")
    print("Q1b All products vs forecast by region:", {r["region"]: r["variance_pct"] for r in k["q1b_total_sales_vs_forecast_by_region"]})
    print("Q1c Beverages vs forecast by region:", {r["region"]: r["variance_pct"] for r in k["q1c_beverages_vs_forecast_by_region"]})
    print("Q2  West stores (promo SKUs):")
    for r in k["q2_west_store_detail"]:
        print(f"    {r['store_id']} {r['store_name']:<20} {r['store_format']:<12} promo {r['variance_pct']:+6.1f}%  "
              f"delayed SKUs {r['delayed_skus_variance_pct']:+6.1f}%  stockout days {r['stockout_days_delayed_skus']}  "
              f"first {r['first_stockout']}")
    print(f"    missed (<= -5%): {k['q2_west_stores_missed_promo_forecast']}")
    print("Q3  PO-4471:", [(r["sku"], r["delay_days"], r["fill_rate"], r["status"]) for r in k["q3_po_4471"]])
    print("Q4  West lost sales on delayed SKUs:", k["q4_west_lost_sales_delayed_skus"])
    print("Q5  Loyalty visits vs prior 4 weeks:", k["q5_loyalty_visits_change_pct_vs_prior_4wk"])
    print("Q6  Northwind late deliveries:")
    for r in k["q6_northwind_late_deliveries"]:
        print(f"    {r['po_number']} {r['dc_id']} promised {r['promised_date']} delivered {r['delivered_date']} "
              f"+{r['delay_days']}d fill {r['avg_fill']:.2f} {r['reason_code']} ({r['lines']} lines)")
