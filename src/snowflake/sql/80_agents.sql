-- Step 80 · Cortex Agents - one per data product that answers questions (core has no agent; it is shared by both).
-- Pinned orchestration model (set snowflake.cortexAgentModel after step 65). Agents run as the CALLER: default role,
-- default warehouse, the caller's row access and masking, and only the search tools the caller may use.
-- @requires CORTEX_AGENT_MODEL

USE ROLE COMMERCIAL_OWNER;
CREATE OR REPLACE AGENT COMMERCIAL.GOLD.COMMERCIAL_ANALYST
  COMMENT = 'Commercial data product: sales and promotions (semantic view) + field notes (one search service per region)'
  PROFILE = '{"display_name": "Contoso Commercial Analyst"}'
  FROM SPECIFICATION $$
models:
  orchestration: "{{CORTEX_AGENT_MODEL}}"
orchestration:
  tool_not_accessible: accept
  budget:
    seconds: 60
    tokens: 32000
instructions:
  orchestration: "Row access already limits every query to the regions this user may see, so 'my region', 'my stores' or 'my area' mean the regions in the data: query without a region filter and answer for the regions that come back. Never ask which region the user means or how much detail they want, and never ask any other clarifying question: choose the most reasonable reading, say in a few words which one you used, and answer. Use CommercialAnalyst for every number: sales, units, net sales, margin, promotions, stores, products and suppliers. Use the FieldNotes tools to explain why something happened (empty shelves, late deliveries, rain checks, store feedback). You only have field-notes tools for the regions the user may see; never guess about other regions. Weeks run Monday to Sunday. The data ends on {{DEMO_WEEK_END}}: 'last week' means {{DEMO_WEEK_START}} to {{DEMO_WEEK_END}}. Holiday Kickoff is promotion {{PROMO_ID}}."
  response: "Lead with the numbers for each region in the data (units, net sales, stores selling), then the reasons. Use at most six sentences or one short table. Cite field notes by note_id. Round money to whole dollars and percentages to one decimal. If some regions are not visible to the user, say so."
  sample_questions:
    - question: "How did Holiday Kickoff do last week in my region, and why?"
    - question: "Holiday Kickoff units and net sales by region last week"
tools:
  - tool_spec:
      type: "cortex_analyst_text_to_sql"
      name: "CommercialAnalyst"
      description: "Sales and promotion numbers by day or week, region, store, store format, product, brand, category and supplier. Includes promotion details such as Holiday Kickoff."
  - tool_spec:
      type: "cortex_search"
      name: "FieldNotesWest"
      description: "Field notes from West stores, the West DC and company-wide notes: shelf availability, deliveries, customer feedback."
  - tool_spec:
      type: "cortex_search"
      name: "FieldNotesEast"
      description: "Field notes from East stores, the East DC and company-wide notes: shelf availability, deliveries, customer feedback."
  - tool_spec:
      type: "cortex_search"
      name: "FieldNotesCentral"
      description: "Field notes from Central stores, the Central DC and company-wide notes."
  - tool_spec:
      type: "cortex_search"
      name: "FieldNotesSouth"
      description: "Field notes from South stores, the South DC and company-wide notes."
tool_resources:
  CommercialAnalyst:
    semantic_view: "COMMERCIAL.GOLD.SV_COMMERCIAL"
    execution_environment:
      type: "warehouse"
      warehouse: "WH_CONTOSO_AGENTS"
      query_timeout: 60
  FieldNotesWest:
    search_service: "COMMERCIAL.GOLD.CSS_FIELD_NOTES_WEST"
    max_results: 5
    id_column: "note_id"
    title_column: "topic"
  FieldNotesEast:
    search_service: "COMMERCIAL.GOLD.CSS_FIELD_NOTES_EAST"
    max_results: 5
    id_column: "note_id"
    title_column: "topic"
  FieldNotesCentral:
    search_service: "COMMERCIAL.GOLD.CSS_FIELD_NOTES_CENTRAL"
    max_results: 5
    id_column: "note_id"
    title_column: "topic"
  FieldNotesSouth:
    search_service: "COMMERCIAL.GOLD.CSS_FIELD_NOTES_SOUTH"
    max_results: 5
    id_column: "note_id"
    title_column: "topic"
$$;

GRANT USAGE ON AGENT COMMERCIAL.GOLD.COMMERCIAL_ANALYST TO ROLE DATA_READER;

USE ROLE LOYALTY_OWNER;
CREATE OR REPLACE AGENT LOYALTY.GOLD.LOYALTY_ANALYST
  COMMENT = 'Loyalty data product: weekly member activity (semantic view). PII is masked by policy.'
  PROFILE = '{"display_name": "Contoso Loyalty Analyst"}'
  FROM SPECIFICATION $$
models:
  orchestration: "{{CORTEX_AGENT_MODEL}}"
orchestration:
  tool_not_accessible: accept
  budget:
    seconds: 60
    tokens: 32000
instructions:
  orchestration: "Row access already limits every query to the regions this user may see, so 'my region' or 'my customers' mean the regions in the data: query without a region filter and never ask which region the user means. Never ask any other clarifying question either: choose the most reasonable reading, say in a few words which one you used, and answer. For a promotion week, unless the user asks for a different comparison, report members' visits and member sales in that week against the average of the four weeks before it, by region and tier. Use LoyaltyAnalyst for every question about loyalty members, visits, tiers, member sales and promotion redemptions. Weeks run Monday to Sunday. The data ends on {{DEMO_WEEK_END}}: 'last week' means the week starting {{DEMO_WEEK_START}}. To judge a week, compare it with the average of the four weeks before it."
  response: "Lead with the numbers. Aggregate by region and tier; never list individual members or personal details. Round percentages to one decimal."
  sample_questions:
    - question: "Did Holiday Kickoff week hurt our loyal customers?"
tools:
  - tool_spec:
      type: "cortex_analyst_text_to_sql"
      name: "LoyaltyAnalyst"
      description: "Loyalty member visits, active members, member sales, beverage sales and promotion redemptions by week, region, tier and home store."
tool_resources:
  LoyaltyAnalyst:
    semantic_view: "LOYALTY.GOLD.SV_LOYALTY"
    execution_environment:
      type: "warehouse"
      warehouse: "WH_CONTOSO_AGENTS"
      query_timeout: 60
$$;

GRANT USAGE ON AGENT LOYALTY.GOLD.LOYALTY_ANALYST TO ROLE LOYALTY_READER;

SHOW AGENTS IN SCHEMA COMMERCIAL.GOLD;
SHOW AGENTS IN SCHEMA LOYALTY.GOLD;
