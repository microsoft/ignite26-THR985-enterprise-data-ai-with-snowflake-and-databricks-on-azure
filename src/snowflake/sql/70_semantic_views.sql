-- Step 70 · Semantic views: the business meaning of each data product, used by Cortex Analyst (design A) and by the
-- Cortex Agents (design B). Callers need SELECT on the semantic view; agents generate SQL against the physical gold
-- tables, so readers also hold SELECT on those (step 50) - and row access applies either way.
-- "Last week" is pinned to the demo week so answers don't depend on today's date.

USE ROLE COMMERCIAL_OWNER;
USE WAREHOUSE {{WAREHOUSE}};

CREATE OR REPLACE SEMANTIC VIEW COMMERCIAL.GOLD.SV_COMMERCIAL
  TABLES (
    sales AS COMMERCIAL.GOLD.FACT_SALES_DAILY
      PRIMARY KEY (sales_date, store_id, sku)
      WITH SYNONYMS ('sales', 'daily sales', 'store sales')
      COMMENT = 'Daily sales by store and SKU. Only rows where units were sold.',
    stores AS CORE.GOLD.DIM_STORE
      PRIMARY KEY (store_id)
      WITH SYNONYMS ('store', 'location', 'shop')
      COMMENT = 'Stores (core data product).',
    products AS CORE.GOLD.DIM_PRODUCT
      PRIMARY KEY (sku)
      WITH SYNONYMS ('product', 'item', 'article')
      COMMENT = 'Products (core data product).',
    suppliers AS CORE.GOLD.DIM_SUPPLIER
      PRIMARY KEY (supplier_id)
      WITH SYNONYMS ('vendor', 'supplier')
      COMMENT = 'Suppliers (core data product).',
    calendar AS CORE.GOLD.DIM_DATE
      PRIMARY KEY (calendar_date)
      COMMENT = 'Calendar (core data product). Weeks run Monday to Sunday.',
    promotions AS COMMERCIAL.GOLD.DIM_PROMOTION
      PRIMARY KEY (promo_id)
      WITH SYNONYMS ('promotion', 'promo', 'campaign', 'deal', 'offer')
      COMMENT = 'Promotions with planned discount and expected lift.'
  )
  RELATIONSHIPS (
    sales_to_stores AS sales (store_id) REFERENCES stores,
    sales_to_products AS sales (sku) REFERENCES products,
    sales_to_calendar AS sales (sales_date) REFERENCES calendar,
    sales_to_promotions AS sales (promo_id) REFERENCES promotions,
    products_to_suppliers AS products (supplier_id) REFERENCES suppliers
  )
  DIMENSIONS (
    sales.sales_date AS sales_date WITH SYNONYMS = ('date', 'day') COMMENT = 'Sales date',
    sales.week_start_date AS week_start_date WITH SYNONYMS = ('week') COMMENT = 'Monday of the sales week',
    sales.region AS region WITH SYNONYMS = ('sales region', 'area') COMMENT = 'Store region: West, East, Central or South',
    sales.promo_id AS promo_id COMMENT = 'Promotion the sale was made under; empty when not on promotion',
    stores.store_id AS store_id COMMENT = 'Store code, for example W04',
    stores.store_name AS store_name COMMENT = 'Store name, for example Contoso Portland',
    stores.store_format AS store_format WITH SYNONYMS = ('format', 'store type') COMMENT = 'Superstore, Neighborhood or Express',
    stores.city AS city COMMENT = 'Store city',
    stores.state AS state COMMENT = 'Store state',
    products.sku AS sku COMMENT = 'Product code, for example BEV001',
    products.product_name AS product_name COMMENT = 'Product name',
    products.brand AS brand COMMENT = 'Brand, for example Northwind Sparkle or Volt Energy',
    products.category AS category COMMENT = 'Product category, for example Beverages',
    products.subcategory AS subcategory COMMENT = 'Product subcategory, for example Sparkling Water',
    suppliers.supplier_name AS supplier_name WITH SYNONYMS = ('vendor name') COMMENT = 'Supplier, for example Northwind Traders',
    calendar.holiday_name AS holiday_name COMMENT = 'Holiday on that date, if any',
    calendar.is_weekend AS is_weekend COMMENT = 'TRUE on Saturday and Sunday',
    promotions.promotion_id AS promo_id COMMENT = 'Promotion code, for example {{PROMO_ID}}',
    promotions.promo_name AS promo_name WITH SYNONYMS = ('promotion name', 'campaign name') COMMENT = 'Promotion name, for example Holiday Kickoff: Sparkling & Energy',
    promotions.promo_type AS promo_type COMMENT = 'TPR (temporary price reduction), BOGO, and so on',
    promotions.promo_start_date AS start_date COMMENT = 'First day of the promotion',
    promotions.promo_end_date AS end_date COMMENT = 'Last day of the promotion',
    promotions.region_scope AS region_scope COMMENT = 'Region the promotion ran in, or All',
    promotions.expected_lift_pct AS expected_lift_pct COMMENT = 'Planned unit lift in percent',
    promotions.discount_pct AS discount_pct COMMENT = 'Discount in percent'
  )
  METRICS (
    sales.total_units AS SUM(units_sold) WITH SYNONYMS = ('units', 'volume', 'units sold') COMMENT = 'Units sold',
    sales.total_net_sales AS SUM(net_sales) WITH SYNONYMS = ('net sales', 'revenue', 'sales dollars') COMMENT = 'Net sales after discounts, USD',
    sales.total_gross_sales AS SUM(gross_sales) COMMENT = 'Gross sales before discounts, USD',
    sales.total_discount AS SUM(discount_amount) COMMENT = 'Discount given, USD',
    sales.total_gross_margin AS SUM(gross_margin) WITH SYNONYMS = ('margin', 'profit') COMMENT = 'Gross margin, USD',
    sales.gross_margin_pct AS SUM(gross_margin) / NULLIF(SUM(net_sales), 0) * 100 COMMENT = 'Gross margin as a percent of net sales',
    sales.stores_selling AS COUNT(DISTINCT store_id) COMMENT = 'Number of stores with sales'
  )
  COMMENT = 'Commercial data product: sales and promotions, joined to the core dimensions. Row access by region applies.'
  AI_SQL_GENERATION 'Weeks run Monday to Sunday. The data ends on {{DEMO_WEEK_END}}: "last week" and "this week" mean {{DEMO_WEEK_START}} to {{DEMO_WEEK_END}}; "the last 4 weeks" means the four weeks before that. Holiday Kickoff is promotion {{PROMO_ID}}: filter promotional sales with sales.promo_id. Region values are West, East, Central and South. Round money to whole dollars and percentages to one decimal. In SEMANTIC_VIEW(...) queries, qualify names only inside the clause (DIMENSIONS stores.store_format METRICS sales.total_units WHERE sales.promo_id = ...); the outer SELECT, WHERE and ORDER BY use the bare output names (SELECT store_format, total_units ... ORDER BY store_format). Metrics such as total_units, total_net_sales and stores_selling exist only in the semantic view, not as table columns.'
  AI_VERIFIED_QUERIES (
    hk_by_region AS (
      QUESTION 'Holiday Kickoff units and net sales by region last week'
      ONBOARDING_QUESTION TRUE
      SQL 'SELECT region, total_units, ROUND(total_net_sales, 0) AS net_sales_usd FROM SEMANTIC_VIEW(COMMERCIAL.GOLD.SV_COMMERCIAL DIMENSIONS sales.region METRICS sales.total_units, sales.total_net_sales WHERE sales.promo_id = ''{{PROMO_ID}}'') ORDER BY region'
    ),
    hk_by_store AS (
      QUESTION 'How did Holiday Kickoff sell by store in my region last week?'
      ONBOARDING_QUESTION TRUE
      SQL 'SELECT store_id, store_name, store_format, total_units, ROUND(total_net_sales, 0) AS net_sales_usd FROM SEMANTIC_VIEW(COMMERCIAL.GOLD.SV_COMMERCIAL DIMENSIONS stores.store_id, stores.store_name, stores.store_format METRICS sales.total_units, sales.total_net_sales WHERE sales.promo_id = ''{{PROMO_ID}}'') ORDER BY store_id'
    ),
    hk_by_sku AS (
      QUESTION 'Which products were in Holiday Kickoff and how did each sell?'
      SQL 'SELECT sku, product_name, brand, total_units, ROUND(total_net_sales, 0) AS net_sales_usd FROM SEMANTIC_VIEW(COMMERCIAL.GOLD.SV_COMMERCIAL DIMENSIONS products.sku, products.product_name, products.brand METRICS sales.total_units, sales.total_net_sales WHERE sales.promo_id = ''{{PROMO_ID}}'') ORDER BY sku'
    ),
    beverages_last_week AS (
      QUESTION 'Beverage units and net sales by region last week'
      SQL 'SELECT region, total_units, ROUND(total_net_sales, 0) AS net_sales_usd FROM SEMANTIC_VIEW(COMMERCIAL.GOLD.SV_COMMERCIAL DIMENSIONS sales.region METRICS sales.total_units, sales.total_net_sales WHERE products.category = ''Beverages'' AND sales.week_start_date = ''{{DEMO_WEEK_START}}''::DATE) ORDER BY region'
    )
  );

GRANT SELECT ON SEMANTIC VIEW COMMERCIAL.GOLD.SV_COMMERCIAL TO ROLE DATA_READER;

USE ROLE LOYALTY_OWNER;
CREATE OR REPLACE SEMANTIC VIEW LOYALTY.GOLD.SV_LOYALTY
  TABLES (
    activity AS LOYALTY.GOLD.FACT_MEMBER_WEEKLY
      PRIMARY KEY (week_start_date, member_id)
      WITH SYNONYMS ('member activity', 'loyalty activity', 'visits')
      COMMENT = 'Weekly activity per loyalty member.',
    members AS LOYALTY.GOLD.DIM_MEMBER
      PRIMARY KEY (member_id)
      WITH SYNONYMS ('member', 'customer', 'loyal customer')
      COMMENT = 'Loyalty members. Personal details are masked for most users.',
    stores AS CORE.GOLD.DIM_STORE
      PRIMARY KEY (store_id)
      WITH SYNONYMS ('home store')
      COMMENT = 'Stores (core data product).'
  )
  RELATIONSHIPS (
    activity_to_members AS activity (member_id) REFERENCES members,
    activity_to_stores AS activity (home_store_id) REFERENCES stores
  )
  DIMENSIONS (
    activity.week_start_date AS week_start_date WITH SYNONYMS = ('week') COMMENT = 'Monday of the activity week',
    activity.home_region AS home_region WITH SYNONYMS = ('region') COMMENT = 'Member''s home region: West, East, Central or South',
    activity.loyalty_tier AS loyalty_tier WITH SYNONYMS = ('tier', 'status') COMMENT = 'Gold, Silver or Bronze',
    members.join_date AS join_date COMMENT = 'Date the member joined',
    members.marketing_opt_in AS marketing_opt_in COMMENT = 'TRUE if the member accepts marketing',
    stores.home_store_name AS store_name COMMENT = 'Member''s home store',
    stores.home_store_format AS store_format COMMENT = 'Superstore, Neighborhood or Express'
  )
  METRICS (
    activity.total_visits AS SUM(visits) WITH SYNONYMS = ('visits', 'trips') COMMENT = 'Store visits',
    activity.active_members AS COUNT(DISTINCT member_id) COMMENT = 'Members with at least one visit that week',
    activity.member_net_sales AS SUM(net_sales) COMMENT = 'Net sales from loyalty members, USD',
    activity.member_beverage_sales AS SUM(beverage_sales) COMMENT = 'Beverage net sales from loyalty members, USD',
    activity.total_promo_redemptions AS SUM(promo_redemptions) COMMENT = 'Promotion redemptions'
  )
  COMMENT = 'Loyalty data product: weekly member activity. Row access by region and PII masking apply.'
  AI_SQL_GENERATION 'Weeks run Monday to Sunday. The data ends on {{DEMO_WEEK_END}}: "last week" means the week starting {{DEMO_WEEK_START}}; compare it with the average of the four weeks before it ({{PRIOR_4WK_START}} onwards) unless asked otherwise. Never return names, emails or phone numbers - aggregate by region and tier. Round percentages to one decimal. In SEMANTIC_VIEW(...) queries, qualify names only inside the clause; the outer SELECT, WHERE and ORDER BY use the bare output names. Metrics exist only in the semantic view, not as table columns.'
  AI_VERIFIED_QUERIES (
    visits_vs_prior_4wk AS (
      QUESTION 'Did Holiday Kickoff week hurt our loyal customers? Visits last week versus the prior 4-week average by region and tier'
      ONBOARDING_QUESTION TRUE
      SQL 'WITH weekly AS (SELECT * FROM SEMANTIC_VIEW(LOYALTY.GOLD.SV_LOYALTY DIMENSIONS activity.home_region, activity.loyalty_tier, activity.week_start_date METRICS activity.total_visits WHERE activity.week_start_date BETWEEN ''{{PRIOR_4WK_START}}''::DATE AND ''{{DEMO_WEEK_START}}''::DATE)) SELECT home_region, loyalty_tier, SUM(IFF(week_start_date = ''{{DEMO_WEEK_START}}''::DATE, total_visits, 0)) AS last_week_visits, SUM(IFF(week_start_date < ''{{DEMO_WEEK_START}}''::DATE, total_visits, 0)) / 4 AS prior_4wk_avg_visits, ROUND((last_week_visits / NULLIF(prior_4wk_avg_visits, 0) - 1) * 100, 1) AS visits_change_pct FROM weekly GROUP BY home_region, loyalty_tier ORDER BY home_region, loyalty_tier'
    )
  );

GRANT SELECT ON SEMANTIC VIEW LOYALTY.GOLD.SV_LOYALTY TO ROLE LOYALTY_READER;

-- Smoke test as the owner (sees every region): expect the answer-key numbers for Holiday Kickoff.
USE ROLE COMMERCIAL_OWNER;
SELECT * FROM SEMANTIC_VIEW(COMMERCIAL.GOLD.SV_COMMERCIAL
  DIMENSIONS sales.region METRICS sales.total_units, sales.total_net_sales
  WHERE sales.promo_id = '{{PROMO_ID}}') ORDER BY region;
