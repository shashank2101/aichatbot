import sqlite3
from app.config import DB_PATHS

_SCHEMA_CACHE = None


def get_connection(store: str) -> sqlite3.Connection:
    """store in {'primary','secondary_east','secondary_west'}"""
    if store not in DB_PATHS:
        raise ValueError(f"Unknown store: {store}")
    conn = sqlite3.connect(DB_PATHS[store])
    conn.row_factory = sqlite3.Row
    return conn


def get_connection_multi(stores: list[str]) -> sqlite3.Connection:
    """
    Opens the first store as the main connection and ATTACHes the rest,
    so the text-to-SQL agent can JOIN across primary + secondary stores
    when a query spans regions (e.g. 'compare discrepancies East vs West').
    Attached schemas are aliased as db_<store_name>.
    """
    stores = list(dict.fromkeys(stores))  # dedupe, keep order
    main = stores[0]
    conn = get_connection(main)
    for s in stores[1:]:
        alias = f"db_{s}"
        conn.execute(f"ATTACH DATABASE ? AS {alias}", (DB_PATHS[s],))
    return conn


def get_schema_text(stores: list[str] | None = None) -> str:
    """
    Returns a human/LLM-readable schema description used by the text-to-SQL
    agent's system prompt (also mirrored in skills/SQL_AGENT_SKILL.md).
    """
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE:
        return _SCHEMA_CACHE
    conn = get_connection("primary")
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cur.fetchall()]
    lines = []
    for t in tables:
        cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
        col_desc = ", ".join(f"{c['name']} {c['type']}" for c in cols)
        lines.append(f"TABLE {t}({col_desc})")
    conn.close()
    _SCHEMA_CACHE = "\n".join(lines)
    return _SCHEMA_CACHE


def run_select(sql: str, stores: list[str]) -> list[dict]:
    """Executes a read-only SELECT against one or more stores (joined via ATTACH)."""
    conn = get_connection_multi(stores) if len(stores) > 1 else get_connection(stores[0])
    try:
        cur = conn.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
        return rows
    finally:
        conn.close()


def log_event(payload: dict):
    """Writes one row to obs_logs on the primary (system-of-record) DB."""
    conn = get_connection("primary")
    cols = ",".join(payload.keys())
    qmarks = ",".join(["?"] * len(payload))
    conn.execute(f"INSERT INTO obs_logs ({cols}) VALUES ({qmarks})", list(payload.values()))
    conn.commit()
    conn.close()
