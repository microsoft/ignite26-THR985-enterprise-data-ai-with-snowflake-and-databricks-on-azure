"""Dimensions, promotions, supplier POs and the store inventory simulation for Contoso Retail."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

import contoso_reference as ref

HK_NAME = "Holiday Kickoff: Sparkling & Energy"
HK_DISCOUNT = 0.25
HK_PLAN_UPLIFT = 1.40
HK_REAL_UPLIFT = {"West": 1.50, "East": 1.58, "Central": 1.42, "South": 1.38}
HK_PO = "PO-4471"
REASONS = ["CARRIER_CAPACITY", "SUPPLIER_SHORTAGE", "WEATHER", "DOCK_CONGESTION"]


@dataclass
class Calendar:
    start: date
    end: date
    monday: date      # Monday of the demo week (the last week of data)
    weeks: int
    days: list        # simulated days (start..end)
    plan_days: list   # simulated days + 2 future weeks (planning horizon)

    def idx(self, d: date) -> int:
        return (d - self.start).days


def make_calendar(end: date, weeks: int) -> Calendar:
    if end.weekday() != 6:
        raise ValueError("--end-date must be a Sunday")
    start = end - timedelta(days=7 * weeks - 1)
    days = [start + timedelta(days=i) for i in range(7 * weeks)]
    plan_days = [start + timedelta(days=i) for i in range(7 * (weeks + 2))]
    return Calendar(start, end, end - timedelta(days=6), weeks, days, plan_days)


def _nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year, month, weekday):
    d = date(year, month + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def holidays(year):
    return {_last_weekday(year, 5, 0): "Memorial Day", date(year, 7, 4): "Independence Day",
            _nth_weekday(year, 9, 0, 1): "Labor Day", date(year, 10, 31): "Halloween",
            date(year, 11, 11): "Veterans Day", _nth_weekday(year, 11, 3, 4): "Thanksgiving"}


def holiday_events(year):
    bev = {s: 1.0 for s in ref.BEVERAGE_SUBCATS}
    snk = {s: 1.0 for s in ref.SNACK_SUBCATS}
    memorial, labor, july4 = _last_weekday(year, 5, 0), _nth_weekday(year, 9, 0, 1), date(year, 7, 4)
    halloween = date(year, 10, 31)
    scale = lambda m, f: {k: f for k in m}
    return [
        (memorial - timedelta(days=3), memorial, {**scale(bev, 1.35), **scale(snk, 1.30), "Bottled Water": 1.40}),
        (july4 - timedelta(days=2), july4, {**scale(bev, 1.50), **scale(snk, 1.45), "Fruit": 1.15, "Ice Cream": 1.30}),
        (labor - timedelta(days=3), labor, {**scale(bev, 1.30), **scale(snk, 1.25)}),
        (halloween - timedelta(days=7), halloween, {"Candy": 2.6, "Chips": 1.1}),
    ]


def build_dim_date(cal: Calendar) -> pd.DataFrame:
    hol = holidays(cal.end.year)
    rows = []
    for d in cal.plan_days:
        iso = d.isocalendar()
        rows.append(dict(date_key=int(d.strftime("%Y%m%d")), date=d, day_of_week=d.isoweekday(), day_name=d.strftime("%A"),
                         week_start_date=d - timedelta(days=d.weekday()), iso_year=iso[0], iso_week=iso[1], month=d.month,
                         month_name=d.strftime("%B"), quarter=(d.month - 1) // 3 + 1, year=d.year,
                         is_weekend=d.weekday() >= 5, holiday_name=hol.get(d)))
    return pd.DataFrame(rows)


def build_stores(rng) -> pd.DataFrame:
    rows = []
    for region in ref.REGIONS:
        for i, (city, state) in enumerate(ref.CITIES[region]):
            fmt = ref.FORMAT_CYCLE[i % 4]
            rows.append(dict(store_id=f"{ref.REGION_CODE[region]}{i + 1:02d}", store_name=f"Contoso {city}", store_format=fmt,
                             city=city, state=state, region=region, dc_id=f"DC-{ref.REGION_CODE[region]}",
                             sqft=int(ref.FORMAT_SQFT[fmt] * rng.uniform(0.9, 1.1) // 100 * 100),
                             open_date=date(int(rng.integers(2005, 2023)), int(rng.integers(1, 13)), int(rng.integers(1, 29)))))
    return pd.DataFrame(rows)


def build_dcs() -> pd.DataFrame:
    return pd.DataFrame(ref.DCS, columns=["dc_id", "dc_name", "city", "state", "region"])


def build_suppliers() -> pd.DataFrame:
    return pd.DataFrame(ref.SUPPLIERS, columns=["supplier_id", "supplier_name", "category", "hq_city", "hq_state", "avg_lead_time_days"])


def build_products(rng) -> pd.DataFrame:
    supplier_of = {cat: sid for sid, _, cat, *_ in ref.SUPPLIERS}
    rows, counters = [], {}
    for cat, code, sub, vel, (lo, hi), brands, items in ref.CATALOG:
        pop = rng.lognormal(0, 0.45, len(items))
        pop = pop / pop.mean()
        for j, item in enumerate(items):
            counters[code] = counters.get(code, 0) + 1
            brand = brands[j % len(brands)]
            plo, phi = next((v for k, v in ref.PRICE_OVERRIDES.items() if k in f" {item}"), (lo, hi))
            price = max(plo - 0.2, math.floor(rng.uniform(plo, phi)) + float(rng.choice([0.29, 0.49, 0.79, 0.99])))
            pl = brand == "Contoso Select"
            cost = round(price * (rng.uniform(0.48, 0.60) if pl else rng.uniform(0.58, 0.74)), 2)
            boost = 1.15 if brand in ("Northwind Sparkle", "Volt Energy") else 1.0
            rows.append(dict(sku=f"{code}{counters[code]:03d}", product_name=f"{brand} {item}", brand=brand, category=cat,
                             subcategory=sub, supplier_id=supplier_of[cat], is_private_label=pl, unit_price=round(price, 2),
                             unit_cost=cost, case_pack=ref.CASE_PACK[cat], status="Active",
                             velocity=vel, popularity=float(pop[j]) * boost))
    return pd.DataFrame(rows)


def demand_factors(cal: Calendar, products: pd.DataFrame, stores: pd.DataFrame, rng):
    """Returns base[S,P], seasonal/event factor[Dp,P] and day-of-week factor[Dp]."""
    size = stores.store_format.map(ref.FORMAT_SIZE).to_numpy() * stores.region.map(ref.REGION_DEMAND).to_numpy()
    cats = list(products.category.unique())
    aff = rng.lognormal(0, 0.08, (len(stores), len(cats)))
    cat_idx = products.category.map({c: i for i, c in enumerate(cats)}).to_numpy()
    base = size[:, None] * (products.velocity * products.popularity).to_numpy()[None, :] * aff[:, cat_idx]

    ords = np.array([d.toordinal() for d in cal.plan_days])
    anchors = [date(cal.end.year, m, 15) for m in range(4, 13)]
    seas = np.ones((len(cal.plan_days), len(products)))
    for sub, table in ref.SEASON.items():
        curve = np.interp(ords, [a.toordinal() for a in anchors], [table.get(a.month, 1.0) for a in anchors])
        seas[:, (products.subcategory == sub).to_numpy()] = curve[:, None]
    for a, b, mults in holiday_events(cal.end.year):
        rows = [i for i, d in enumerate(cal.plan_days) if a <= d <= b]
        for sub, m in mults.items():
            cols = np.where((products.subcategory == sub).to_numpy())[0]
            if rows and len(cols):
                seas[np.ix_(rows, cols)] *= m
    dow = np.array([ref.DOW[d.weekday()] for d in cal.plan_days]) / np.mean(ref.DOW)
    return base, seas, dow


def build_promotions(cal: Calendar, products: pd.DataFrame, stores: pd.DataFrame, rng):
    Dp, S, P = len(cal.plan_days), len(stores), len(products)
    plan_up = np.ones((Dp, S, P), np.float32)
    real_up = np.ones((Dp, S, P), np.float32)
    disc = np.zeros((Dp, S, P), np.float32)
    pidx = np.full((Dp, S, P), -1, np.int16)
    region_of = stores.region.to_numpy()
    cat_of = dict(zip(products.subcategory, products.category))
    subcats = list(products.subcategory.unique())
    promos, bridge, used = [], [], set()

    def add(pid, name, ptype, d, start, end, scope, sub, cat, skus, plan, real, funding):
        k = len(promos)
        promos.append(dict(promo_id=pid, promo_name=name, promo_type=ptype, discount_pct=round(d * 100, 1), start_date=start,
                           end_date=end, region_scope=scope, category=cat, subcategory=sub,
                           expected_lift_pct=int(round((plan - 1) * 100)), funding_type=funding))
        bridge.extend(dict(promo_id=pid, sku=products.sku[p]) for p in skus)
        days = list(range(cal.idx(start), min(cal.idx(end), Dp - 1) + 1))
        for region, r_up in real.items():
            ix = np.ix_(days, np.where(region_of == region)[0], list(skus))
            plan_up[ix], real_up[ix], disc[ix], pidx[ix] = plan, r_up, d, k

    W = cal.weeks
    for w in range(W + 2):
        ws = cal.start + timedelta(days=7 * w)
        for n in range(int(rng.choice([2, 3]))):
            for _ in range(25):
                sub = subcats[int(rng.integers(len(subcats)))]
                if w >= W - 2 and cat_of[sub] == "Beverages":
                    continue  # keep the planted beverage story clean
                scope = "All" if rng.random() < 0.55 else ref.REGIONS[int(rng.integers(4))]
                regions = ref.REGIONS if scope == "All" else [scope]
                weeks = [w, w + 1] if rng.random() < 0.1 else [w]
                if not any((x, r, sub) in used for x in weeks + [w - 1] for r in regions):
                    break
            else:
                continue
            used.update((x, r, sub) for x in weeks for r in regions)
            ptype = str(rng.choice(["TPR", "Digital Coupon", "Bundle"], p=[0.7, 0.15, 0.15]))
            d = float(rng.choice([0.10, 0.15, 0.20, 0.25, 0.30], p=[0.25, 0.30, 0.25, 0.12, 0.08]))
            plan = 1 + ref.PROMO_LIFT_K[ptype] * d
            cand = products.index[products.subcategory == sub].to_numpy()
            skus = np.sort(rng.choice(cand, min(len(cand), int(rng.integers(3, 7))), replace=False))
            name = str(rng.choice(ref.PROMO_NAMES[ptype])).format(sub=sub)
            funding = str(rng.choice(["Vendor-funded", "Retailer-funded"], p=[0.6, 0.4]))
            real = {r: plan if w == W - 1 else plan * float(rng.lognormal(0, 0.10)) for r in regions}  # quiet demo week
            add(f"PR-{ws:%y%m%d}-{n + 1}", name, ptype, d, ws, ws + timedelta(days=7 * len(weeks) - 1), scope, sub,
                cat_of[sub], skus, plan, real, funding)

    sw = products[(products.subcategory == "Sparkling Water") & (products.brand == "Northwind Sparkle")]
    sw = sw.sort_values("popularity", ascending=False)
    en = products[products.subcategory == "Energy Drinks"].sort_values("popularity", ascending=False).head(4)
    hk_skus = list(sw.index) + list(en.index)
    hk = dict(promo_id=f"PR-{cal.monday:%y%m%d}-HK", skus=hk_skus, constrained=list(sw.index[:3]) + list(en.index[:2]))
    add(hk["promo_id"], HK_NAME, "TPR", HK_DISCOUNT, cal.monday, cal.end, "All", "Sparkling Water, Energy Drinks",
        "Beverages", hk_skus, HK_PLAN_UPLIFT, HK_REAL_UPLIFT, "Vendor-funded")
    return pd.DataFrame(promos), pd.DataFrame(bridge), plan_up, real_up, disc, pidx, hk


def build_pos(cal: Calendar, products: pd.DataFrame, stores: pd.DataFrame, lam_plan, hk, rng):
    """Supplier→DC purchase orders, plus the DC→store fill-rate grid [D,S,P] they imply."""
    D, S, P = len(cal.days), len(stores), len(products)
    fill = np.ones((D, S, P), np.float32)
    fill[rng.random((D, S, P)) < 0.008] = 0.5  # routine short shipments
    region_of = stores.region.to_numpy()
    constrained = set(hk["constrained"])
    july4_week = cal.idx(date(cal.end.year, 7, 4)) // 7
    events = {("SUP01", "DC-S", july4_week)}  # an earlier Northwind slip before July 4th
    while len(events) < 5:
        sup = ref.SUPPLIERS[int(rng.integers(1, len(ref.SUPPLIERS)))][0]
        events.add((sup, ref.DCS[int(rng.integers(4))][0], int(rng.integers(2, cal.weeks - 4))))

    def constrain(region, p, d0, d1, value):
        a, b = max(cal.idx(d0), 0), min(cal.idx(d1), D - 1)
        if a <= b:
            sm = region_of == region
            fill[a:b + 1, sm, p] = np.minimum(fill[a:b + 1, sm, p], value)

    rows, seq = [], 0

    def add_po(po, sup, dc, region, lines, order_date, promised, delay, fills, reason, qty, dry_fill=0.1):
        for ln, p in enumerate(lines):
            f = fills[p]
            arrive = promised + timedelta(days=delay)
            delivered = arrive if arrive <= cal.end else None
            if delivered is None:
                status = "Open" if promised > cal.end else "In transit"
            else:
                status = {(True, True): "Delivered", (False, True): "Late", (True, False): "Partial",
                          (False, False): "Late - Partial"}[(delay == 0, f >= 0.98)]
            rows.append(dict(po_number=po, po_line=ln + 1, supplier_id=sup, dc_id=dc, sku=products.sku[p], order_date=order_date,
                             promised_date=promised, delivered_date=delivered, ordered_qty=int(qty[p]),
                             delivered_qty=int(round(qty[p] * f)) if delivered else None, delay_days=delay if delivered else None,
                             fill_rate=round(f, 3) if delivered else None, status=status,
                             reason_code=None if status in ("Delivered", "Open", "In transit")
                             else (reason if delay > 0 else "SUPPLIER_SHORTAGE")))
            if delay >= 3:  # DC runs dry after its safety stock is gone
                constrain(region, p, promised + timedelta(days=2), arrive - timedelta(days=1),
                          dry_fill if f < 0.9 else 0.5)
            if f < 0.98:
                constrain(region, p, arrive, arrive + timedelta(days=1), f)

    for w in range(cal.weeks + 2):
        ws = cal.start + timedelta(days=7 * w)
        days = slice(7 * w, 7 * w + 7)
        for sid, _, cat, _, _, lead in ref.SUPPLIERS:
            order_date = ws - timedelta(days=10)
            if order_date > cal.end:
                continue
            promised = order_date + timedelta(days=lead)
            sup_skus = products.index[products.supplier_id == sid].to_numpy()
            case = ref.CASE_PACK[cat]
            for dc, _, _, _, region in ref.DCS:
                sm = np.where(region_of == region)[0]
                q = np.ceil(lam_plan[days][:, sm][:, :, sup_skus].sum(axis=(0, 1)) * 1.05 / case) * case
                qty = dict(zip(sup_skus, q))
                planted = w == cal.weeks - 1 and sid == "SUP01" and dc == "DC-W"
                lines = [p for p in sup_skus if not (planted and p in constrained)]
                delay = int(rng.choice([0, 1, 2, 3], p=[0.80, 0.12, 0.06, 0.02]))
                fills = {p: 1.0 if rng.random() < 0.85 else float(rng.uniform(0.90, 0.99)) for p in sup_skus}
                reason = str(rng.choice(REASONS))
                if (sid, dc, w) in events:
                    delay = int(rng.integers(4, 8))
                    for p in rng.choice(sup_skus, int(rng.integers(3, 6)), replace=False):
                        fills[p] = float(rng.uniform(0.35, 0.60))
                if sid == "SUP01" and cal.weeks - 2 <= w <= cal.weeks:
                    # Keep Northwind clean around the demo week; the next West PO lands with PO-4471.
                    delay = 1 if (dc == "DC-W" and w == cal.weeks) else 0
                    fills = {p: 1.0 for p in sup_skus}
                    reason = "CARRIER_CAPACITY"
                seq += 1
                add_po(f"PO-{1000 + seq}", sid, dc, region, lines, order_date, promised, delay, fills, reason, qty)
                if planted:
                    hk_lines = [p for p in sup_skus if p in constrained]
                    add_po(HK_PO, sid, dc, region, hk_lines, cal.monday - timedelta(days=10),
                           cal.monday - timedelta(days=4), 8, {p: 0.75 for p in hk_lines}, "CARRIER_CAPACITY", qty,
                           dry_fill=0.0)
    return pd.DataFrame(rows), fill


def simulate_inventory(cal: Calendar, stores: pd.DataFrame, lam_plan, demand, fill):
    """Daily order-up-to replenishment with next-day DC delivery; sales are capped by stock on hand."""
    D, S, P = demand.shape
    Dp = lam_plan.shape[0]
    tdos = stores.store_format.map(ref.FORMAT_TARGET_DOS).to_numpy()
    cs = np.concatenate([np.zeros((1, S, P)), np.cumsum(lam_plan, axis=0)])
    si, pj = np.arange(S)[:, None], np.arange(P)[None, :]

    def cover(h):
        return cs[np.minimum(h + tdos, Dp)[:, None], si, pj] - cs[min(h, Dp)]

    on_hand = np.round(cover(0))
    incoming = np.zeros((S, P))
    out = {k: np.zeros((D, S, P), np.float32) for k in ("on_hand", "received", "sold", "on_order")}
    stockout = np.zeros((D, S, P), bool)
    for d in range(D):
        on_hand += incoming
        out["received"][d] = incoming
        sold = np.minimum(demand[d], on_hand)
        on_hand -= sold
        stockout[d] = (demand[d] > sold) | (on_hand <= 0)
        incoming = np.floor(np.maximum(0.0, np.ceil(cover(d + 1) - on_hand)) * fill[d])
        out["sold"][d], out["on_hand"][d], out["on_order"][d] = sold, on_hand, incoming
    nxt = (cs[np.minimum(np.arange(D) + 8, Dp)] - cs[np.arange(D) + 1]) / 7
    out["days_of_supply"] = np.round(out["on_hand"] / np.maximum(nxt, 0.01), 1)
    out["stockout"] = stockout
    return out
