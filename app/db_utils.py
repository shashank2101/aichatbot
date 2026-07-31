import sqlite3
import datetime
from app.config import DB_PATHS

_SCHEMA_CACHE = None

_CHAT_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    username TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_history_session_user_id
ON chat_history (session_id, username, id);
"""


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


def save_chat_message(session_id: str, username: str, role: str, content: str) -> None:
    """Persist one user or assistant message for a browser chat session."""
    if role not in {"user", "assistant"}:
        raise ValueError("Chat message role must be 'user' or 'assistant'")

    conn = get_connection("primary")
    try:
        conn.executescript(_CHAT_HISTORY_SCHEMA)
        conn.execute(
            """INSERT INTO chat_history (session_id, username, role, content, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, username, role, content, datetime.datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


def get_chat_history(session_id: str, username: str, limit: int = 10) -> list[dict]:
    """Return the newest messages for a user's session in chronological order."""
    if limit < 1:
        return []

    conn = get_connection("primary")
    try:
        conn.executescript(_CHAT_HISTORY_SCHEMA)
        rows = conn.execute(
            """SELECT role, content, created_at
               FROM chat_history
               WHERE session_id = ? AND username = ?
               ORDER BY id DESC
               LIMIT ?""",
            (session_id, username, limit),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]
    finally:
        conn.close()


def get_chat_sessions(username: str, limit: int = 50) -> list[dict]:
    """Return a user's sessions, newest first, with a preview of each latest message."""
    if limit < 1:
        return []

    conn = get_connection("primary")
    try:
        conn.executescript(_CHAT_HISTORY_SCHEMA)
        rows = conn.execute(
            """SELECT history.session_id, history.content AS preview, history.created_at AS updated_at
               FROM chat_history AS history
               INNER JOIN (
                   SELECT session_id, MAX(id) AS latest_id
                   FROM chat_history
                   WHERE username = ?
                   GROUP BY session_id
               ) AS latest ON history.id = latest.latest_id
               WHERE history.username = ?
               ORDER BY history.id DESC
               LIMIT ?""",
            (username, username, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
