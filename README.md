# CDE Management System

**Find and govern your Critical Data Elements: scan every column in the warehouse against CDE reference patterns with Cortex LLMs, and manage the findings in one app.**

## Overview

The Critical Data Elements (CDE) Management System is a Streamlit-in-Snowflake application that helps data governance teams discover where critical data actually lives. It scans columns across databases and schemas, uses Snowflake Cortex LLMs to match each column against governed CDE reference patterns (customer identifiers, account numbers, payment data and similar), and records the results as findings that stewards can review and manage. Reference data — the pattern register itself — is maintained in the same app, and an "Ask Cortex AI" page lets stewards question the findings in natural language.

## Problem

Regulated organisations must know exactly which columns hold critical data elements: they drive masking policy, access control, retention and audit. In practice:

- CDE inventories are built by spreadsheet archaeology and are stale the day they are finished.
- New tables and columns land daily; nobody re-surveys the estate by hand.
- Column names lie — `CUST_ID`, `CLIENT_REF` and `PARTY_NO` can all be the same CDE — so pattern matching on names alone misses matches and invents false ones.

Discovery needed to be continuous, semantic (not just name-based), and tied to a review workflow stewards actually use.

## Architecture

```
 Reference patterns register ──────────────┐
 (CDE name, definition, sample patterns,   │
  sensitivity, matching guidance)          │
                                           ▼
 Warehouse columns ──► CDE Scan ──► Cortex LLM matching
 (INFORMATION_SCHEMA   (per DB/     (column + pattern in,
  across DBs/schemas)   schema)      match + rationale out)
                                           │
                                           ▼
                                     Findings table
                                           │
        ┌──────────────────┬───────────────┴───────────────┐
        ▼                  ▼                               ▼
  Reference Data      Findings page                   Ask Cortex AI
  Management page     (review / confirm /             (natural-language
  (maintain patterns)  reject matches)                 questions)
```

- **Reference data** — the CDE pattern register: one row per CDE with example patterns and matching guidance for the LLM (see `sql/reference_patterns.sql`).
- **Scan** — enumerates columns from `INFORMATION_SCHEMA`, then asks a Cortex LLM, per column, whether it matches each candidate CDE pattern, returning a match decision and rationale (see `sql/cde_scan.sql`).
- **Model check** — before scanning, the app detects which Cortex models are available in the current account, because model availability varies by account and region.
- **Findings** — every match lands as a finding with status (proposed / confirmed / rejected) for steward review in the app.

## Tech Stack

- Snowflake Cortex LLM functions (COMPLETE) and Snowpark
- Streamlit in Snowflake
- Snowflake `INFORMATION_SCHEMA`
- SQL, Python

## Key Components

| Component | Description |
|---|---|
| `sql/reference_patterns.sql` | DDL and seed rows for the CDE reference pattern register, and the findings table. |
| `sql/cde_scan.sql` | The scan queries: column enumeration and the Cortex LLM matching prompt pattern. |
| `app/streamlit_app.py` | The four-page app: Reference Data Management, CDE Scan, Findings, Ask Cortex AI. Includes per-account Cortex model availability detection. |

## How It Works

1. A steward maintains the CDE register on the Reference Data Management page — adding new CDEs with example patterns and matching guidance as policy evolves.
2. On the CDE Scan page, the steward picks a database/schema. The app first checks which Cortex models the account can use, then runs the scan.
3. Each column is matched against the register by a Cortex LLM, which returns a structured decision — matched CDE, confidence, rationale — rather than a bare name-pattern hit.
4. Matches are written to the findings table as *proposed*. On the Findings page, stewards confirm or reject each one; only confirmed findings feed downstream masking and access policy.
5. The Ask Cortex AI page answers questions over the confirmed findings ("which databases hold payment card data?") for reporting and audit.

## Outcomes

- CDE discovery moved from a periodic manual survey to an on-demand scan stewards can re-run whenever the estate changes.
- Semantic matching catches columns whose names do not obviously match the CDE, which name-pattern scans missed.
- Every proposed match carries the LLM's rationale and a human confirm/reject decision, keeping an auditable line between machine suggestion and governed fact.

## Repo Structure

```
cde-management-system/
├── README.md
├── sql/
│   ├── reference_patterns.sql  # CDE register + findings table DDL and seeds
│   └── cde_scan.sql            # column enumeration + Cortex LLM matching
└── app/
    └── streamlit_app.py        # 4-page Streamlit-in-Snowflake app
```

## Note

Portfolio project based on production work in regulated financial services; code is a clean-room representative implementation with sample/synthetic metadata only.
