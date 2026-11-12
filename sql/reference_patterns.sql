-- ============================================================================
-- CDE reference pattern register and findings table.
--
-- The register is the governed source of truth for what counts as a Critical
-- Data Element: one row per CDE, with example column patterns and matching
-- guidance that is passed to the Cortex LLM during a scan.
-- All values below are sample/synthetic.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS GOVERNANCE_DB;
CREATE SCHEMA IF NOT EXISTS GOVERNANCE_DB.CDE;

-- ----------------------------------------------------------------------------
-- Reference pattern register
-- ----------------------------------------------------------------------------

CREATE OR REPLACE TABLE GOVERNANCE_DB.CDE.CDE_REFERENCE_PATTERNS (
    cde_name            STRING        NOT NULL,   -- e.g. CUSTOMER_IDENTIFIER
    cde_description     STRING        NOT NULL,   -- what the element means
    example_patterns    STRING        NOT NULL,   -- comma-separated name hints
    matching_guidance   STRING        NOT NULL,   -- instructions for the LLM
    sensitivity_level   STRING        NOT NULL,   -- HIGH / MEDIUM / LOW
    is_active           BOOLEAN       DEFAULT TRUE,
    updated_at          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

INSERT INTO GOVERNANCE_DB.CDE.CDE_REFERENCE_PATTERNS
    (cde_name, cde_description, example_patterns, matching_guidance, sensitivity_level)
VALUES
    ('CUSTOMER_IDENTIFIER',
     'Unique identifier of a customer or client party.',
     'CUST_ID, CUSTOMER_ID, CLIENT_REF, PARTY_NO, CLIENT_ID',
     'Match columns that uniquely identify a customer, client or party, '
     'including abbreviated or legacy naming. Do not match generic row IDs '
     'on non-customer tables.',
     'HIGH'),
    ('ACCOUNT_NUMBER',
     'Financial account number held by a customer.',
     'ACCT_NO, ACCOUNT_NUMBER, ACCT_NUM, IBAN',
     'Match columns holding bank, investment or loan account numbers. '
     'Do not match internal surrogate keys or transaction IDs.',
     'HIGH'),
    ('PAYMENT_CARD_NUMBER',
     'Payment card number (PAN).',
     'CARD_NO, PAN, CARD_NUMBER, CC_NUM',
     'Match columns that store primary account numbers for payment cards. '
     'Do not match last-four-digits-only columns; those are a separate CDE.',
     'HIGH'),
    ('CUSTOMER_NAME',
     'Full legal or display name of a customer.',
     'CUST_NAME, CUSTOMER_NAME, CLIENT_NAME, FULL_NAME',
     'Match columns holding a person''s name on customer/party tables. '
     'Do not match product, branch or file names.',
     'MEDIUM'),
    ('DATE_OF_BIRTH',
     'Date of birth of an individual.',
     'DOB, DATE_OF_BIRTH, BIRTH_DT, BIRTH_DATE',
     'Match columns storing an individual''s birth date. Do not match '
     'account open dates or transaction dates.',
     'HIGH');

-- ----------------------------------------------------------------------------
-- Findings: one row per proposed/confirmed column-to-CDE match
-- ----------------------------------------------------------------------------

CREATE OR REPLACE TABLE GOVERNANCE_DB.CDE.CDE_FINDINGS (
    finding_id        NUMBER AUTOINCREMENT,
    database_name     STRING NOT NULL,
    schema_name       STRING NOT NULL,
    table_name        STRING NOT NULL,
    column_name       STRING NOT NULL,
    column_comment    STRING,
    cde_name          STRING NOT NULL,
    confidence        STRING,            -- HIGH / MEDIUM / LOW from the LLM
    rationale         STRING,            -- LLM's reason for the match
    model_used        STRING,            -- Cortex model that produced it
    status            STRING DEFAULT 'PROPOSED',  -- PROPOSED/CONFIRMED/REJECTED
    reviewed_by       STRING,
    reviewed_at       TIMESTAMP_NTZ,
    found_at          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
