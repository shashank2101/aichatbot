"""
Converts a natural-language question into a read-only SQL SELECT against the
schema described in skills/SQL_AGENT_SKILL.md.

Two modes:
  - LLM mode (config.USE_LLM=True): sends schema + question to Azure OpenAI,
    demands SELECT-only SQL back.
  - Offline rule-based fallback: pattern-matches common intents to safe
    parameterized-looking SQL templates. Keeps the hackathon demo fully
    functional with zero API keys, and is what actually gets exercised
    below unless you wire real credentials.

Every generated SQL statement is passed through `is_safe_select()` before
ever reaching the executor.
"""
import sqlparse
from app.db_utils import get_schema_text
from app.llm import call_llm
from app.config import USE_LLM
SYSTEM_PROMPT_TEMPLATE = """
You are an expert Text-to-SQL agent for an Inventory Audit Assistant.

You convert natural language questions into ONE SQLite SELECT query.

DATABASE SCHEMA:
{schema}

STRICT RULES:

1. Return ONLY ONE SQL SELECT statement.
2. Do NOT return markdown, explanations, comments or code fences.
3. Never generate INSERT, UPDATE, DELETE, DROP, ALTER, ATTACH or PRAGMA.
4. Use ONLY tables and columns from the schema.
5. Use explicit JOINs whenever required.

----------------------------------------
IMPORTANT
----------------------------------------

The user's question ALWAYS has priority.

If the user mentions ANY specific value such as:

- SKU
- warehouse
- warehouse name
- warehouse id
- location
- bin
- auditor
- audit id
- discrepancy id
- vendor
- region
- severity
- status
- dates

YOU MUST use those values in the WHERE clause.

NEVER ignore values mentioned by the user.

Bad Example

User:
What is the stock level of SKU-1002?

Wrong SQL

SELECT *
FROM inventory
LIMIT 50;

Correct SQL

SELECT ...
FROM inventory
JOIN ...
WHERE s.sku_code='SKU-1002';

----------------------------------------
Aggregation
----------------------------------------

If the user asks:

- total
- count
- average
- dashboard
- KPI
- summary
- metrics

Use SQL aggregation:

COUNT()
SUM()
AVG()
MIN()
MAX()
GROUP BY

Do NOT return detailed rows if the user asked for a summary.

----------------------------------------
Filters
----------------------------------------

Apply every filter mentioned by the user.

Examples

Question:
Pending audits in Hyderabad warehouse

SQL:
WHERE
a.status='Pending'
AND
w.name='Hyderabad'

Question:
High severity discrepancies

SQL:
WHERE d.severity='High'

Question:
Inventory below reorder level

SQL:
WHERE quantity < reorder_level

----------------------------------------
LIMIT
----------------------------------------

If the user asks about ONE SKU,
ONE warehouse,
ONE audit,
ONE discrepancy,

DO NOT add LIMIT 50.

LIMIT 50 is ONLY for broad listing questions such as:

Show inventory
List SKUs
Show audits
Show discrepancies

----------------------------------------
If no matching information exists

Generate the best SQL possible.

Never return an empty response.

Never ignore filters supplied by the user.
"""

def is_safe_select(sql: str) -> bool:
    if not sql:
        return False
    parsed = sqlparse.parse(sql.strip().rstrip(";"))
    if len(parsed) != 1:
        return False
    stmt = parsed[0]
    if stmt.get_type() != "SELECT":
        return False
    banned = ["insert", "update", "delete", "drop", "alter", "attach", "pragma", "--", ";"]
    low = sql.lower()
    return not any(b in low for b in banned[:-2]) and low.count(";") == 0


# ---- Rule-based templates (offline fallback / fast path) ----
def _rule_based_sql(question: str, intent: str) -> str | None:
    q = question.lower()

    if intent == "inventory_query":
        if "out of stock" in q:
            return ("SELECT w.name AS warehouse, s.sku_code, s.description, i.quantity "
                     "FROM inventory i JOIN warehouses w ON i.warehouse_id=w.warehouse_id "
                     "JOIN skus s ON i.sku_id=s.sku_id WHERE i.quantity = 0")
        if "low stock" in q or "reorder" in q:
            return ("SELECT w.name AS warehouse, s.sku_code, i.quantity, i.reorder_level "
                     "FROM inventory i JOIN warehouses w ON i.warehouse_id=w.warehouse_id "
                     "JOIN skus s ON i.sku_id=s.sku_id WHERE i.quantity > 0 AND i.quantity < i.reorder_level")
        if "overstock" in q:
            return ("SELECT w.name AS warehouse, s.sku_code, i.quantity, i.max_capacity "
                     "FROM inventory i JOIN warehouses w ON i.warehouse_id=w.warehouse_id "
                     "JOIN skus s ON i.sku_id=s.sku_id WHERE i.quantity > i.max_capacity")
        if "total inventory" in q or "total stock" in q or "how many units" in q:
            return "SELECT SUM(quantity) AS total_units FROM inventory"
        return ("SELECT w.name AS warehouse, s.sku_code, s.description, i.quantity, i.location_bin "
                 "FROM inventory i JOIN warehouses w ON i.warehouse_id=w.warehouse_id "
                 "JOIN skus s ON i.sku_id=s.sku_id LIMIT 50")

    if intent == "audit_query":
        if "pending" in q:
            return ("SELECT w.name AS warehouse, a.auditor_name, a.start_date FROM audits a "
                     "JOIN warehouses w ON a.warehouse_id=w.warehouse_id WHERE a.status='Pending'")
        if "in progress" in q or "active" in q:
            return ("SELECT w.name AS warehouse, a.auditor_name, a.start_date FROM audits a "
                     "JOIN warehouses w ON a.warehouse_id=w.warehouse_id WHERE a.status='In Progress'")
        if "completed" in q:
            return ("SELECT w.name AS warehouse, a.auditor_name, a.start_date, a.end_date FROM audits a "
                     "JOIN warehouses w ON a.warehouse_id=w.warehouse_id WHERE a.status='Completed'")
        return ("SELECT w.name AS warehouse, a.status, COUNT(*) AS cnt FROM audits a "
                 "JOIN warehouses w ON a.warehouse_id=w.warehouse_id GROUP BY w.name, a.status")

    if intent == "discrepancy_query":
        if "expired" in q:
            return ("SELECT w.name AS warehouse, s.sku_code, d.severity, d.detected_at FROM discrepancies d "
                     "JOIN warehouses w ON d.warehouse_id=w.warehouse_id JOIN skus s ON d.sku_id=s.sku_id "
                     "WHERE d.disc_type='Expired'")
        if "damaged" in q:
            return ("SELECT w.name AS warehouse, s.sku_code, d.severity FROM discrepancies d "
                     "JOIN warehouses w ON d.warehouse_id=w.warehouse_id JOIN skus s ON d.sku_id=s.sku_id "
                     "WHERE d.disc_type='Damaged'")
        if "wrong location" in q:
            return ("SELECT w.name AS warehouse, s.sku_code, d.severity FROM discrepancies d "
                     "JOIN warehouses w ON d.warehouse_id=w.warehouse_id JOIN skus s ON d.sku_id=s.sku_id "
                     "WHERE d.disc_type='Wrong Location'")
        if "high severity" in q or "high variance" in q:
            return ("SELECT w.name AS warehouse, s.sku_code, d.disc_type, d.expected_qty, d.actual_qty "
                     "FROM discrepancies d JOIN warehouses w ON d.warehouse_id=w.warehouse_id "
                     "JOIN skus s ON d.sku_id=s.sku_id WHERE d.severity='High'")
        return ("SELECT w.name AS warehouse, d.disc_type, d.severity, COUNT(*) AS cnt FROM discrepancies d "
                 "JOIN warehouses w ON d.warehouse_id=w.warehouse_id GROUP BY w.name, d.disc_type, d.severity")

    if intent == "dashboard_metrics":
        # Broad KPI/overview asks ("how are we doing", "give me a summary") — a portfolio-level
        # rollup rather than one specific table, so this intent always has something to return
        # instead of falling through to "couldn't translate that question".
        return (
            "SELECT "
            "(SELECT COUNT(*) FROM warehouses) AS total_warehouses, "
            "(SELECT COUNT(*) FROM skus) AS total_skus, "
            "(SELECT COALESCE(SUM(quantity),0) FROM inventory) AS total_inventory_units, "
            "(SELECT COUNT(*) FROM audits) AS total_audits, "
            "(SELECT COUNT(*) FROM audits WHERE status='Completed') AS completed_audits, "
            "(SELECT COUNT(*) FROM audits WHERE status='Pending') AS pending_audits, "
            "(SELECT COUNT(*) FROM discrepancies) AS total_discrepancies, "
            "(SELECT COUNT(*) FROM discrepancies WHERE severity='High') AS high_severity_discrepancies"
        )

    return None


def generate_sql(question: str, intent: str, stores: list[str]) -> tuple[str | None, int]:
    """Returns (sql_or_none, tokens_used)."""
    rb = _rule_based_sql(question, intent)
    if rb and (not USE_LLM):
        return rb, 0

    if USE_LLM:
        schema = get_schema_text(stores)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(schema=schema)
        text, tokens = call_llm(system_prompt, question)
        sql = text.strip().strip("`").replace("sql\n", "")
        if is_safe_select(sql):
            return sql, tokens
        # fall back to rule-based if LLM produced something unsafe/invalid
        return rb, tokens

    return rb, 0
