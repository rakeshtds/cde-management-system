-- ============================================================================
-- CDE scan queries.
--
-- Step 1 enumerates candidate columns for a database/schema.
-- Step 2 matches each column against the CDE register with a Cortex LLM:
-- the model receives the column's name, table context and comment plus the
-- register's matching guidance, and returns a structured decision.
-- All names are sample/synthetic.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Step 1: enumerate columns to scan (example target: ANALYTICS_DB.PUBLIC)
-- ----------------------------------------------------------------------------

SELECT
    table_catalog   AS database_name,
    table_schema    AS schema_name,
    table_name,
    column_name,
    comment         AS column_comment
FROM ANALYTICS_DB.INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = 'PUBLIC'
ORDER BY table_name, ordinal_position;

-- ----------------------------------------------------------------------------
-- Step 2: LLM matching. One call per column against the full active register.
-- The prompt asks for a strict JSON decision so results can be parsed and
-- written to GOVERNANCE_DB.CDE.CDE_FINDINGS.
-- ----------------------------------------------------------------------------

WITH columns_to_scan AS (
    SELECT
        table_catalog   AS database_name,
        table_schema    AS schema_name,
        table_name,
        column_name,
        comment         AS column_comment
    FROM ANALYTICS_DB.INFORMATION_SCHEMA.COLUMNS
    WHERE table_schema = 'PUBLIC'
),
register AS (
    SELECT LISTAGG(
               cde_name || ' — ' || cde_description
               || ' | example patterns: ' || example_patterns
               || ' | guidance: ' || matching_guidance,
               '\n'
           ) AS register_text
    FROM GOVERNANCE_DB.CDE.CDE_REFERENCE_PATTERNS
    WHERE is_active
)
SELECT
    c.database_name,
    c.schema_name,
    c.table_name,
    c.column_name,
    c.column_comment,
    SNOWFLAKE.CORTEX.COMPLETE(
        '<MODEL_NAME>',  -- replaced by the app with an account-available model
        'You are a data governance classifier. Decide whether the column '
        || 'below matches one of the Critical Data Elements in the register.\n\n'
        || 'REGISTER:\n' || r.register_text || '\n\n'
        || 'COLUMN:\n'
        || 'table: ' || c.table_name || '\n'
        || 'column: ' || c.column_name || '\n'
        || 'comment: ' || COALESCE(c.column_comment, '(none)') || '\n\n'
        || 'Respond with ONLY a JSON object: '
        || '{"matched_cde": "<CDE name or null>", '
        || '"confidence": "HIGH|MEDIUM|LOW", '
        || '"rationale": "<one sentence>"}'
    ) AS llm_decision
FROM columns_to_scan c
CROSS JOIN register r;

-- ----------------------------------------------------------------------------
-- Step 3 (illustrative): parsed decisions ready to insert as findings.
-- The Streamlit app performs this parse in Python so malformed responses
-- can be logged and skipped instead of failing the scan.
-- ----------------------------------------------------------------------------

-- INSERT INTO GOVERNANCE_DB.CDE.CDE_FINDINGS
--     (database_name, schema_name, table_name, column_name, column_comment,
--      cde_name, confidence, rationale, model_used, status)
-- SELECT ..., 'PROPOSED' FROM <parsed scan results>
-- WHERE matched_cde IS NOT NULL;
