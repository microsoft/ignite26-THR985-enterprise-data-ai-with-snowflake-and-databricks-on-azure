# Contoso Retail — synthetic data for THR985

Deterministic, fictitious retail data for the demo. Every name, email (`example.com`) and phone number (`555-01xx`) is made up.

```
python generate_contoso_retail.py            # seed 42, ~10 s, ~23 MB of Parquet in ./data
python generate_contoso_retail.py --end-date 2026-11-22   # shifts the demo week; planted dates move with it
```
Outputs: `data/<platform>/<data_product>/<table>.parquet`, `data/manifest.json`, `data/answer_key.json` (expected demo answers, computed from the published tables).

## The company
48 stores in 4 US regions (12 each: 3 Superstore, 6 Neighborhood, 3 Express) · 4 DCs · 8 suppliers · 200 SKUs in 8 categories · 20,000 loyalty members · 26 weeks of history (May 18 – Nov 15, 2026) plus 2 future weeks of forecasts and open POs.

## Data products — one writer each
| Writer | Data product | Tables (rows) | Agent behind MCP |
|---|---|---|---|
| Snowflake | **core** (conformed, shared) | dim_date (196), dim_store (48), dim_dc (4), dim_supplier (8), dim_product (200) | — used by every product |
| Snowflake | **commercial** | fact_sales_daily (1.54M), dim_promotion (73), bridge_promotion_sku (330), field_notes (163) | Cortex Agent "Commercial Analyst": semantic view + Cortex Search over field_notes |
| Snowflake | **loyalty** (PII) | dim_member (20k), fact_member_weekly (282k) | Cortex Agent "Loyalty Analyst": masking on name, email, phone, birth year |
| Databricks | **demand_forecast** | fact_demand_forecast_weekly (269k) | Genie Agent "Demand Forecast": plus governed views over federated commercial + core |
| Databricks | **supply_chain** | fact_inventory_daily (1.75M), fact_supplier_po (22.4k) | Genie Agent "Supply Chain" |

**Bring your own compute:** Databricks reads core + commercial through catalog federation (it needs actuals to score its forecast). Snowflake can read Databricks products through a catalog-linked database (optional).

## Table guide
| Table | Key columns | Notes |
|---|---|---|
| dim_store | store_id (W01…S12), store_name, store_format, region, dc_id | West superstores: W01, W05, W09 |
| dim_product | sku (BEV001…), product_name, brand, category, subcategory, supplier_id, unit_price, unit_cost | Northwind Traders supplies all beverages |
| fact_sales_daily | date, store_id, sku, units_sold, gross_sales, discount_amount, net_sales, cogs, gross_margin, promo_id | Rows only where units sold > 0; sales are capped by stock on hand |
| dim_promotion / bridge_promotion_sku | promo_id, promo_name, promo_type, discount_pct, start/end_date, region_scope, expected_lift_pct, funding_type | Random weekly promos + the planted Holiday Kickoff |
| field_notes | note_id, note_ts, note_date, region, store_id, author_role, topic, promo_id, note_text | Unstructured corpus for Cortex Search |
| dim_member | member_id, first_name, last_name, email, phone, birth_year, loyalty_tier, home_store_id, home_region | **PII** → masking policies |
| fact_member_weekly | week_start_date, member_id, home_store_id, visits, net_sales, beverage_sales, promo_redemptions | |
| fact_demand_forecast_weekly | forecast_week_start, store_id, sku, forecast_units, p10, p90, promo_flag, model_name, model_version, generated_at | Unconstrained demand; includes 2 future weeks |
| fact_inventory_daily | date, store_id, sku, on_hand_units, on_order_units, received_units, stockout_flag, days_of_supply | End-of-day snapshot |
| fact_supplier_po | po_number, po_line, supplier_id, dc_id, sku, order/promised/delivered_date, ordered/delivered_qty, delay_days, fill_rate, status, reason_code | Supplier → DC |

Row-level security: region (`dim_store.region`, `dim_member.home_region`). Personas: **Ava** (West region manager), **Ben** (East analyst).

## The planted story — demo week Nov 9–15, 2026
1. **Oct 28** — "Holiday Kickoff" (`PR-261109-HK`) approved: 25% off 8 SKUs (4 Northwind Sparkle sparkling water, 4 Volt Energy), all regions, expected lift 40%.
2. **Nov 6** — Northwind's promo allocation PO **PO-4471** to DC-West slips (carrier capacity): promised Nov 5, delivered **Nov 13 (+8 days) at 75% fill**, 5 SKUs.
3. **Nov 9–13** — DC-West has none of those 5 SKUs. West Express stores run out on day 1, Neighborhood stores by Nov 10–11; superstores hold on deeper backroom stock.
4. West demand was there (superstores beat forecast), but West misses overall; East beats forecast on the same promo.
5. Field notes (empty shelves, rain checks), West Gold loyalty visits, and a precedent (Northwind 6 days late to DC-South before July 4) echo the story.

## Demo questions and expected answers (`answer_key.json`)
**"How did Holiday Kickoff do last week in my region, and why?"**
- **Ava (West):** −9.4% vs forecast (9,691 vs 10,691 units). **9 of 12 West stores missed** — all Neighborhood and Express stores; superstores held. Cause: PO-4471 arrived 8 days late and 75% filled, so the 5 SKUs stocked out from Nov 9–10. About **1,650 units / $7.5K** of promo sales lost.
- **Ben (East):** **+12.0%** vs forecast (11,869 vs 10,596); no supply issues. (Central +3.2%, South +2.0%.)

| Store | Format | Promo vs forecast | Delayed SKUs vs forecast | Stockout days | First stockout |
|---|---|---|---|---|---|
| W01 Seattle | Superstore | +19.5% | +13.6% | 1 | Nov 13 |
| W02 Tacoma | Neighborhood | −15.0% | −21.8% | 4 | Nov 10 |
| W03 Spokane | Neighborhood | −21.1% | −29.9% | 4 | Nov 10 |
| W04 Portland | Express | −40.2% | −51.4% | 6 | Nov 9 |
| W05 Eugene | Superstore | +9.7% | +3.1% | 0 | — |
| W06 Boise | Neighborhood | −9.9% | −23.0% | 4 | Nov 10 |
| W07 Sacramento | Neighborhood | −20.5% | −26.0% | 3 | Nov 11 |
| W08 San Jose | Express | −31.0% | −42.2% | 6 | Nov 9 |
| W09 Fresno | Superstore | −3.5% | −6.0% | 0 | — |
| W10 Reno | Neighborhood | −22.1% | −35.7% | 4 | Nov 10 |
| W11 Phoenix | Neighborhood | −24.9% | −43.2% | 5 | Nov 9 |
| W12 Tucson | Express | −34.9% | −53.9% | 6 | Nov 9 |

**Follow-ups**
- "Which region missed its beverage forecast?" → West −3.7% (East +5.4%, South +2.2%, Central +1.4%). All products: West −2.0%.
- "Did it hurt our loyal customers?" → West Gold visits **−13.1%** vs the prior 4 weeks (Silver −6.4%, Bronze −5.1%); East up 2–5%.
- "Has Northwind done this before?" → PO-1196 to DC-South: promised Jun 25, delivered Jul 1 (+6 days, 92% fill), the week of July 4.

Re-check these numbers whenever you regenerate with different parameters (the generator prints them).

## MCP topology used in the demo — one server per data product
| MCP endpoint | Platform | Agent | Data products | Registered in Foundry as |
|---|---|---|---|---|
| Snowflake-managed MCP server (`CORTEX_AGENT_RUN` only) | Snowflake (GA) | Commercial Analyst | commercial + core | Commercial agent |
| Snowflake-managed MCP server (`CORTEX_AGENT_RUN` only) | Snowflake (GA) | Loyalty Analyst | loyalty + core | Loyalty agent |
| Genie Agent MCP (`/api/2.0/mcp/genie/{id}`) | Databricks (Preview) | Demand Forecast | demand_forecast + governed views on federated commercial/core | Forecast agent |
| Genie Agent MCP | Databricks (Preview) | Supply Chain | supply_chain + core | Supply chain agent |

For comparison on the slide: one Snowflake MCP server exposing both Cortex Agents, and Databricks Genie One for workspace-wide questions.

## Loading (outline for the PoC)
- **Snowflake:** stage the Parquet files → create Snowflake-managed Iceberg tables on an external volume (`dfs` endpoint) → load from the stage. Add row access by region and masking on `dim_member` PII.
- **Databricks:** upload to a Unity Catalog volume → `CREATE TABLE … AS SELECT * FROM read_files(...)` (managed tables). Expose governed views (region filter) over the federated Snowflake tables for the Genie Agents.
