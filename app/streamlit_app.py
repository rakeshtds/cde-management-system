"""CDE Management System — Streamlit in Snowflake.

Four pages:
  1. Reference Data Management — maintain the CDE pattern register.
  2. CDE Scan                  — scan a database/schema; Cortex LLMs match
                                 columns against the register.
  3. Findings                  — review proposed matches; confirm or reject.
  4. Ask Cortex AI             — natural-language questions over findings.

Before scanning, the app detects which Cortex models are available in the
current account (availability varies by account/region) and only offers
models that answer a probe call.
"""

from __future__ import annotations

import json

import streamlit as st
from snowflake.snowpark.context import get_active_session

# Candidate Cortex models, most capable first. Availability is probed at
# runtime; the app never assumes a model exists in this account.
CANDIDATE_MODELS = [
    "llama3.1-405b",
    "llama3.1-70b",
    "mistral-large2",
    "mixtral-8x7b",
    "llama3.1-8b",
]

session = get_active_session()


# ---------------------------------------------------------------------------
# Model availability
# ---------------------------------------------------------------------------


@st.cache_data(ttl=3600)
def available_models() -> list[str]:
    """Probe each candidate model with a minimal Cortex COMPLETE call."""
    found: list[str] = []
    for model in CANDIDATE_MODELS:
        try:
            session.sql(
                "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, 'Reply with: ok')",
                params=[model],
            ).collect()
            found.append(model)
        except Exception:
            continue  # model not enabled in this account/region
    return found


# ---------------------------------------------------------------------------
# Page 1: Reference Data Management
# ---------------------------------------------------------------------------


def page_reference_data() -> None:
    st.header("Reference Data Management")
    st.caption("The governed CDE register that scans match against.")

    patterns = session.table("GOVERNANCE_DB.CDE.CDE_REFERENCE_PATTERNS").to_pandas()
    st.dataframe(patterns, use_container_width=True)

    st.subheader("Add a CDE pattern")
    with st.form("add_pattern"):
        cde_name = st.text_input("CDE name", placeholder="e.g. EMAIL_ADDRESS")
        description = st.text_area("Description")
        examples = st.text_input("Example column patterns (comma-separated)")
        guidance = st.text_area("Matching guidance for the LLM")
        sensitivity = st.selectbox("Sensitivity", ["HIGH", "MEDIUM", "LOW"])
        if st.form_submit_button("Add pattern"):
            session.sql(
                """
                INSERT INTO GOVERNANCE_DB.CDE.CDE_REFERENCE_PATTERNS
                    (cde_name, cde_description, example_patterns,
                     matching_guidance, sensitivity_level)
                VALUES (?, ?, ?, ?, ?)
                """,
                params=[cde_name, description, examples, guidance, sensitivity],
            ).collect()
            st.success(f"Added CDE pattern: {cde_name}")
            st.cache_data.clear()


# ---------------------------------------------------------------------------
# Page 2: CDE Scan
# ---------------------------------------------------------------------------


def _scan_columns(database: str, schema: str, model: str) -> int:
    """Match every column in database.schema against the register.

    Returns the number of proposed findings written.
    """
    columns = session.sql(
        f"""
        SELECT table_name, column_name, comment AS column_comment
        FROM {database}.INFORMATION_SCHEMA.COLUMNS
        WHERE table_schema = ?
        ORDER BY table_name, ordinal_position
        """,
        params=[schema],
    ).collect()

    register = session.sql(
        """
        SELECT LISTAGG(
                   cde_name || ' — ' || cde_description
                   || ' | example patterns: ' || example_patterns
                   || ' | guidance: ' || matching_guidance, '\n')
        FROM GOVERNANCE_DB.CDE.CDE_REFERENCE_PATTERNS
        WHERE is_active
        """
    ).collect()[0][0]

    written = 0
    for row in columns:
        prompt = (
            "You are a data governance classifier. Decide whether the column "
            "below matches one of the Critical Data Elements in the register."
            f"\n\nREGISTER:\n{register}\n\nCOLUMN:\n"
            f"table: {row['TABLE_NAME']}\n"
            f"column: {row['COLUMN_NAME']}\n"
            f"comment: {row['COLUMN_COMMENT'] or '(none)'}\n\n"
            'Respond with ONLY a JSON object: {"matched_cde": "<CDE name or '
            'null>", "confidence": "HIGH|MEDIUM|LOW", "rationale": "<one '
            'sentence>"}'
        )
        raw = session.sql(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?)",
            params=[model, prompt],
        ).collect()[0][0]
        try:
            decision = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue  # log-and-skip malformed responses; never fail the scan
        if not decision.get("matched_cde"):
            continue
        session.sql(
            """
            INSERT INTO GOVERNANCE_DB.CDE.CDE_FINDINGS
                (database_name, schema_name, table_name, column_name,
                 column_comment, cde_name, confidence, rationale,
                 model_used, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPOSED')
            """,
            params=[
                database,
                schema,
                row["TABLE_NAME"],
                row["COLUMN_NAME"],
                row["COLUMN_COMMENT"],
                decision["matched_cde"],
                decision.get("confidence"),
                decision.get("rationale"),
                model,
            ],
        ).collect()
        written += 1
    return written


def page_scan() -> None:
    st.header("CDE Scan")
    models = available_models()
    if not models:
        st.error("No Cortex models are available in this account.")
        return
    st.caption(f"Cortex models available in this account: {', '.join(models)}")

    database = st.text_input("Database", placeholder="e.g. ANALYTICS_DB")
    schema = st.text_input("Schema", placeholder="e.g. PUBLIC")
    model = st.selectbox("Matching model", models)
    if st.button("Run scan") and database and schema:
        with st.spinner("Scanning columns and matching against the register…"):
            count = _scan_columns(database.upper(), schema.upper(), model)
        st.success(f"Scan complete — {count} proposed finding(s) written.")


# ---------------------------------------------------------------------------
# Page 3: Findings
# ---------------------------------------------------------------------------


def page_findings() -> None:
    st.header("Findings")
    status = st.selectbox(
        "Status", ["PROPOSED", "CONFIRMED", "REJECTED"], index=0
    )
    findings = session.sql(
        """
        SELECT finding_id, database_name, schema_name, table_name,
               column_name, cde_name, confidence, rationale, model_used
        FROM GOVERNANCE_DB.CDE.CDE_FINDINGS
        WHERE status = ?
        ORDER BY found_at DESC
        """,
        params=[status],
    ).to_pandas()
    st.dataframe(findings, use_container_width=True)

    if status == "PROPOSED" and not findings.empty:
        st.subheader("Review a finding")
        finding_id = st.number_input(
            "Finding ID", min_value=int(findings["FINDING_ID"].min()),
            max_value=int(findings["FINDING_ID"].max()),
        )
        col1, col2 = st.columns(2)
        for label, new_status in [("Confirm", "CONFIRMED"), ("Reject", "REJECTED")]:
            column = col1 if label == "Confirm" else col2
            if column.button(label):
                session.sql(
                    """
                    UPDATE GOVERNANCE_DB.CDE.CDE_FINDINGS
                    SET status = ?, reviewed_by = CURRENT_USER(),
                        reviewed_at = CURRENT_TIMESTAMP()
                    WHERE finding_id = ?
                    """,
                    params=[new_status, int(finding_id)],
                ).collect()
                st.success(f"Finding {finding_id} marked {new_status}.")
                st.rerun()


# ---------------------------------------------------------------------------
# Page 4: Ask Cortex AI
# ---------------------------------------------------------------------------


def page_ask() -> None:
    st.header("Ask Cortex AI")
    st.caption("Questions are answered over confirmed findings only.")
    question = st.text_input(
        "Ask about critical data in the estate",
        placeholder="e.g. Which databases hold payment card data?",
    )
    if st.button("Ask") and question:
        findings = session.sql(
            """
            SELECT database_name, schema_name, table_name, column_name, cde_name
            FROM GOVERNANCE_DB.CDE.CDE_FINDINGS
            WHERE status = 'CONFIRMED'
            """
        ).collect()
        context = "\n".join(
            f"{r['DATABASE_NAME']}.{r['SCHEMA_NAME']}.{r['TABLE_NAME']}."
            f"{r['COLUMN_NAME']} -> {r['CDE_NAME']}"
            for r in findings
        )
        model = available_models()[0]
        answer = session.sql(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?)",
            params=[
                model,
                "Answer the question using ONLY the confirmed CDE findings "
                f"below.\n\nFINDINGS:\n{context}\n\nQUESTION: {question}",
            ],
        ).collect()[0][0]
        st.write(answer)


# ---------------------------------------------------------------------------
# App shell
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="CDE Management System", layout="wide")
    st.title("Critical Data Elements — Management System")
    page = st.sidebar.radio(
        "Page",
        [
            "Reference Data Management",
            "CDE Scan",
            "Findings",
            "Ask Cortex AI",
        ],
    )
    {
        "Reference Data Management": page_reference_data,
        "CDE Scan": page_scan,
        "Findings": page_findings,
        "Ask Cortex AI": page_ask,
    }[page]()


if __name__ == "__main__":
    main()
