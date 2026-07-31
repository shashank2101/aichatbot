"""
Runs BETWEEN text-to-SQL and execution/answer-generation.

1. Table gate: if the SQL references a table the role can't access at all,
   block execution entirely and return a denial message (never touches SQL exec).
2. Column mask: after execution, strip sensitive columns (e.g. unit_price,
   unit_cost) from the row dicts before they are ever handed to the LLM for
   answer generation, based on role.
"""
import re
from app import rbac

TABLE_NAME_RE = re.compile(r"\bFROM\s+([a-zA-Z_]+)|\bJOIN\s+([a-zA-Z_]+)", re.IGNORECASE)


def extract_tables(sql: str) -> set:
    tables = set()
    for m in TABLE_NAME_RE.finditer(sql):
        t = m.group(1) or m.group(2)
        if t:
            tables.add(t.lower())
    return tables


def check_table_access(sql: str, role: str) -> tuple[bool, str | None]:
    tables = extract_tables(sql)
    for t in tables:
        if not rbac.table_allowed(role, t):
            return False, rbac.denial_message(role, t)
    return True, None


def mask_rows(rows: list[dict], role: str) -> list[dict]:
    """Strips sensitive columns per-table role rules. Rows here are already
    flattened (joined) dicts, so we mask by column NAME (unit_price/unit_cost)
    which is sufficient since those names are unique to the skus table."""
    masked_cols = set()
    for table in ("skus",):
        masked_cols |= rbac.masked_columns(role, table)
    if not masked_cols:
        return rows
    cleaned = []
    for r in rows:
        cleaned.append({k: v for k, v in r.items() if k not in masked_cols})
    return cleaned
