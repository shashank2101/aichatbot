"""
Simulates the "button click on another page" that pushes ERP/Oracle-sourced
JSON records into the PRIMARY warehouse DB, then synchronizes the relevant
subset down into the correct SECONDARY store DB based on warehouse region.

Pipeline stages (as required):
  ✔ Validate JSON            -> pydantic already guarantees shape (schemas.py)
  ✔ Check required fields    -> _validate_record
  ✔ Remove duplicates        -> dedupe on (warehouse_id, sku_code)
  ✔ Convert datatypes        -> _coerce_types
  ✔ Validate quantity        -> must be int >= 0
  ✔ Validate warehouse       -> must exist in warehouses table
  ✔ Validate SKU             -> must exist / match SKU-#### pattern
  ✔ Synchronize latest inventory -> upsert into primary.inventory
  ✔ Insert/Update database   -> primary + relevant secondary
"""
import re
import csv
import io
import datetime
from app.db_utils import get_connection
from app.config import REGION_TO_STORE

SKU_RE = re.compile(r"^SKU-\d{3,6}$")

# Columns a CSV upload may provide. warehouse_id/sku_code/quantity are
# required (mirrors IngestPayloadItem); the rest are optional.
_CSV_FIELDS = {"warehouse_id", "sku_code", "quantity", "location_bin", "source_system"}


def parse_csv_records(file_bytes: bytes) -> tuple[list[dict], list[dict]]:
    """Parses an uploaded CSV file into the same record shape process_ingest_push()
    expects. Returns (records, parse_errors) — parse_errors are rows that couldn't
    even be read (e.g. missing header), separate from validation rejects which
    process_ingest_push() itself reports.
    """
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    parse_errors = []
    records = []
    if reader.fieldnames is None:
        return [], [{"row": None, "reason": "CSV has no header row"}]

    header = {h.strip().lower() for h in reader.fieldnames if h}
    if not {"warehouse_id", "sku_code", "quantity"}.issubset(header):
        return [], [{"row": None, "reason": "CSV header must include warehouse_id, sku_code, quantity"}]

    for i, row in enumerate(reader, start=2):  # start=2: header is row 1
        clean = {(k or "").strip().lower(): (v.strip() if isinstance(v, str) else v)
                 for k, v in row.items() if k}
        rec = {k: v for k, v in clean.items() if k in _CSV_FIELDS and v not in (None, "")}
        if not rec.get("warehouse_id") or not rec.get("sku_code") or rec.get("quantity") in (None, ""):
            parse_errors.append({"row": i, "reason": "missing warehouse_id/sku_code/quantity"})
            continue
        records.append(rec)
    return records, parse_errors


def _coerce_types(rec: dict) -> dict:
    rec = dict(rec)
    rec["warehouse_id"] = int(rec["warehouse_id"])
    rec["quantity"] = int(rec["quantity"])
    rec["sku_code"] = str(rec["sku_code"]).strip().upper()
    return rec


def _validate_record(rec: dict, valid_warehouse_ids: set, valid_sku_codes: dict) -> tuple[bool, str]:
    required = ["warehouse_id", "sku_code", "quantity"]
    for f in required:
        if rec.get(f) in (None, ""):
            return False, f"missing required field '{f}'"
    if rec["quantity"] < 0:
        return False, "quantity must be >= 0"
    if rec["warehouse_id"] not in valid_warehouse_ids:
        return False, f"unknown warehouse_id {rec['warehouse_id']}"
    if not SKU_RE.match(rec["sku_code"]):
        return False, f"invalid SKU code format '{rec['sku_code']}'"
    if rec["sku_code"] not in valid_sku_codes:
        return False, f"SKU '{rec['sku_code']}' not found in master data"
    return True, "ok"


def process_ingest_push(records: list[dict]) -> dict:
    conn = get_connection("primary")
    valid_wh = {r["warehouse_id"]: r["region"] for r in conn.execute("SELECT warehouse_id, region FROM warehouses").fetchall()}
    sku_map = {r["sku_code"]: r["sku_id"] for r in conn.execute("SELECT sku_id, sku_code FROM skus").fetchall()}

    accepted, rejected, seen = [], [], set()
    for raw in records:
        try:
            rec = _coerce_types(raw)
        except (ValueError, TypeError) as e:
            rejected.append({"record": raw, "reason": f"type conversion failed: {e}"})
            continue

        dedupe_key = (rec["warehouse_id"], rec["sku_code"])
        if dedupe_key in seen:
            rejected.append({"record": raw, "reason": "duplicate record in this batch"})
            continue
        seen.add(dedupe_key)

        ok, reason = _validate_record(rec, set(valid_wh.keys()), sku_map)
        if not ok:
            rejected.append({"record": raw, "reason": reason})
            continue
        accepted.append(rec)

    now = datetime.datetime.now().isoformat(timespec="seconds")
    synced_secondary = {"secondary_east": 0, "secondary_west": 0}

    for rec in accepted:
        sku_id = sku_map[rec["sku_code"]]
        existing = conn.execute(
            "SELECT inv_id FROM inventory WHERE warehouse_id=? AND sku_id=?",
            (rec["warehouse_id"], sku_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE inventory SET quantity=?, location_bin=COALESCE(?, location_bin), last_updated=? WHERE inv_id=?",
                (rec["quantity"], rec.get("location_bin"), now, existing["inv_id"]),
            )
        else:
            conn.execute(
                """INSERT INTO inventory (warehouse_id, sku_id, quantity, reorder_level, max_capacity,
                                           location_bin, expiry_date, last_updated)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (rec["warehouse_id"], sku_id, rec["quantity"], 30, 800, rec.get("location_bin"), None, now),
            )
        conn.execute(
            "INSERT INTO sync_log (source_db, target_db, record_type, record_id, synced_at, status) VALUES (?,?,?,?,?,?)",
            (rec.get("source_system", "ERP"), "primary", "inventory", sku_id, now, "SUCCESS"),
        )

        # push down to the correct secondary store based on warehouse region
        region = valid_wh[rec["warehouse_id"]]
        target_store = REGION_TO_STORE.get(region)
        if target_store and target_store != "primary":
            sconn = get_connection(target_store)
            s_existing = sconn.execute(
                "SELECT inv_id FROM inventory WHERE warehouse_id=? AND sku_id=?",
                (rec["warehouse_id"], sku_id),
            ).fetchone()
            if s_existing:
                sconn.execute(
                    "UPDATE inventory SET quantity=?, location_bin=COALESCE(?, location_bin), last_updated=? WHERE inv_id=?",
                    (rec["quantity"], rec.get("location_bin"), now, s_existing["inv_id"]),
                )
            else:
                sconn.execute(
                    """INSERT INTO inventory (warehouse_id, sku_id, quantity, reorder_level, max_capacity,
                                               location_bin, expiry_date, last_updated)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (rec["warehouse_id"], sku_id, rec["quantity"], 30, 800, rec.get("location_bin"), None, now),
                )
            sconn.execute(
                "INSERT INTO sync_log (source_db, target_db, record_type, record_id, synced_at, status) VALUES (?,?,?,?,?,?)",
                ("primary", target_store, "inventory", sku_id, now, "SUCCESS"),
            )
            sconn.commit()
            sconn.close()
            synced_secondary[target_store] = synced_secondary.get(target_store, 0) + 1

    conn.commit()
    conn.close()

    return {
        "accepted": len(accepted),
        "rejected": len(rejected),
        "rejected_details": rejected,
        "synced_to_secondary": synced_secondary,
    }
