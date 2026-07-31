"""
Exports the current contents of the SQLite stores to CSV files under
sample_data/ — a static, prebuilt snapshot you can show/attach to explain
"this is the kind of data the system works with" (e.g. in a demo or
competition), without wiring up a live DB->CSV sync.

Usage:
    python scripts/export_sample_data.py

Re-run any time you want to refresh the snapshot from the current DB state
(e.g. after scripts/init_db.py or an ingest push). Safe to re-run — it only
overwrites files under sample_data/, never touches db/*.db.
"""
import csv
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from application.config import DB_PATHS  # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "sample_data")

# users/obs_logs are consolidation-only + carry credentials/PII-ish data (password
# hashes, question text) — excluded from the "sample dataset" export on purpose.
TABLES_TO_EXPORT = ["warehouses", "skus", "inventory", "audits", "discrepancies", "sync_log"]


def export_store(store_name: str, db_path: str):
    if not os.path.exists(db_path):
        print(f"  skip {store_name}: {db_path} not found")
        return
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    existing_tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }

    store_dir = os.path.join(OUT_DIR, store_name)
    os.makedirs(store_dir, exist_ok=True)

    for table in TABLES_TO_EXPORT:
        if table not in existing_tables:
            continue
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        out_path = os.path.join(store_dir, f"{table}.csv")
        with open(out_path, "w", newline="") as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                for r in rows:
                    writer.writerow(dict(r))
            else:
                cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
                writer = csv.writer(f)
                writer.writerow(cols)
        print(f"  wrote {out_path} ({len(rows)} rows)")

    conn.close()


if __name__ == "__main__":
    print(f"Exporting sample CSV datasets to {OUT_DIR} ...")
    for store, path in DB_PATHS.items():
        print(f"[{store}]")
        export_store(store, path)
    print("Done.")
