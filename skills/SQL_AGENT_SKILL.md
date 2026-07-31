# Text-to-SQL Agent — Schema Reference

This mirrors the schema `app/db_utils.get_schema_text()` generates live from
SQLite at runtime (via `PRAGMA table_info`), so it's always accurate to the
actual DB — this file is documentation only, not loaded by code.

See `DB_SCHEMA.md` at the project root for the full table/column reference
and relationships.

Generated SQL must always be read-only `SELECT` — enforced in code by
`text2sql_agent.is_safe_select()`, which rejects anything that isn't a single
SELECT statement or that contains INSERT/UPDATE/DELETE/DROP/ALTER/ATTACH/PRAGMA.
