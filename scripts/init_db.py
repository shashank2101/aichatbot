"""
Creates and seeds the 3 SQLite stores (primary, secondary_east, secondary_west)
with the exact schema referenced across app/*.py and app/agents/*.py.

Run once from the project root:
    python scripts/init_db.py
Safe to re-run: drops and recreates all tables each time.
"""
import os
import sys
import sqlite3
import hashlib
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import DB_PATHS  # noqa: E402

PRIMARY_SCHEMA = """
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,              -- admin | manager | auditor | viewer
    region TEXT,                     -- WEST | EAST | CENTRAL | SOUTH | NULL (admin)
    full_name TEXT NOT NULL
);

CREATE TABLE warehouses (
    warehouse_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    region TEXT NOT NULL,            -- SOUTH | WEST | EAST | CENTRAL
    capacity_units INTEGER NOT NULL
);

CREATE TABLE skus (
    sku_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku_code TEXT UNIQUE NOT NULL,   -- format SKU-####
    description TEXT NOT NULL,
    unit_price REAL NOT NULL,
    unit_cost REAL NOT NULL
);

CREATE TABLE inventory (
    inv_id INTEGER PRIMARY KEY AUTOINCREMENT,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    sku_id INTEGER NOT NULL REFERENCES skus(sku_id),
    quantity INTEGER NOT NULL,
    reorder_level INTEGER NOT NULL,
    max_capacity INTEGER NOT NULL,
    location_bin TEXT,
    expiry_date TEXT,                -- ISO date or NULL
    last_updated TEXT NOT NULL
);

CREATE TABLE audits (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    auditor_name TEXT NOT NULL,
    status TEXT NOT NULL,            -- Pending | In Progress | Completed
    start_date TEXT NOT NULL,
    end_date TEXT
);

CREATE TABLE discrepancies (
    disc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    sku_id INTEGER NOT NULL REFERENCES skus(sku_id),
    disc_type TEXT NOT NULL,         -- Quantity Mismatch | Wrong Location | Damaged | Expired | High Variance
    severity TEXT NOT NULL,          -- High | Medium | Low
    expected_qty INTEGER,
    actual_qty INTEGER,
    detected_at TEXT NOT NULL
);

CREATE TABLE sync_log (
    sync_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_db TEXT NOT NULL,
    target_db TEXT NOT NULL,
    record_type TEXT NOT NULL,
    record_id INTEGER,
    synced_at TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE obs_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    question TEXT,
    intent TEXT,
    generated_sql TEXT,
    cache_hit INTEGER,
    jailbreak_flag INTEGER,
    latency_ms INTEGER,
    tokens_used INTEGER,
    thumbs TEXT,
    satisfied INTEGER,
    retries INTEGER,
    created_at TEXT
);

CREATE TABLE chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    username TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_chat_history_session_user_id
ON chat_history (session_id, username, id);
"""

# Secondary stores hold a regional slice: mirrored master data (warehouses,
# skus) needed for JOINs, plus the live inventory/sync_log they own.
SECONDARY_SCHEMA = """
CREATE TABLE warehouses (
    warehouse_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    capacity_units INTEGER NOT NULL
);

CREATE TABLE skus (
    sku_id INTEGER PRIMARY KEY,
    sku_code TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    unit_price REAL NOT NULL,
    unit_cost REAL NOT NULL
);

CREATE TABLE inventory (
    inv_id INTEGER PRIMARY KEY AUTOINCREMENT,
    warehouse_id INTEGER NOT NULL,
    sku_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    reorder_level INTEGER NOT NULL,
    max_capacity INTEGER NOT NULL,
    location_bin TEXT,
    expiry_date TEXT,
    last_updated TEXT NOT NULL
);

CREATE TABLE sync_log (
    sync_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_db TEXT NOT NULL,
    target_db TEXT NOT NULL,
    record_type TEXT NOT NULL,
    record_id INTEGER,
    synced_at TEXT NOT NULL,
    status TEXT NOT NULL
);
"""


def pw(p):
    return hashlib.sha256(p.encode()).hexdigest()


def build_primary(path):
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.executescript(PRIMARY_SCHEMA)

    now = datetime.datetime.now().isoformat(timespec="seconds")
    today = datetime.date.today()

    # ---- users ----
    users = [
        ("admin", pw("admin"), "admin", None, "Ahana Rao"),
        ("manager1", pw("manager1"), "manager", "WEST", "Vikram Shah"),
        ("manager2", pw("manager2"), "manager", "EAST", "Priya Nair"),
        ("auditor1", pw("auditor1"), "auditor", "SOUTH", "Sameer Iyer"),
        ("viewer1", pw("viewer1"), "viewer", "WEST", "Neha Kapoor"),
    ]
    conn.executemany(
        "INSERT INTO users (username,password_hash,role,region,full_name) VALUES (?,?,?,?,?)", users
    )

    # ---- warehouses ---- (SOUTH = Hyderabad DC / primary's own region)
    warehouses = [
        ("Hyderabad DC", "SOUTH", 50000),
        ("Mumbai Hub", "WEST", 40000),
        ("Pune Satellite", "WEST", 20000),
        ("Kolkata Hub", "EAST", 35000),
        ("Bhubaneswar Satellite", "EAST", 15000),
        ("Nagpur Central", "CENTRAL", 30000),
    ]
    conn.executemany(
        "INSERT INTO warehouses (name,region,capacity_units) VALUES (?,?,?)", warehouses
    )
    wh_ids = [r[0] for r in conn.execute("SELECT warehouse_id FROM warehouses ORDER BY warehouse_id").fetchall()]

    # ---- skus ----
    skus = [
        ("SKU-1001", "Wireless Mouse", 799.0, 420.0),
        ("SKU-1002", "USB-C Cable 1m", 299.0, 110.0),
        ("SKU-1003", "27in Monitor", 15999.0, 11200.0),
        ("SKU-1004", "Mechanical Keyboard", 3499.0, 2100.0),
        ("SKU-1005", "Laptop Stand", 1299.0, 650.0),
        ("SKU-1006", "Webcam 1080p", 2199.0, 1300.0),
        ("SKU-1007", "External SSD 1TB", 6999.0, 5100.0),
        ("SKU-1008", "Office Chair", 8999.0, 6200.0),
        ("SKU-1009", "Whiteboard Marker Set", 249.0, 90.0),
        ("SKU-1010", "A4 Paper Ream", 349.0, 210.0),
    ]
    conn.executemany(
        "INSERT INTO skus (sku_code,description,unit_price,unit_cost) VALUES (?,?,?,?)", skus
    )
    sku_ids = [r[0] for r in conn.execute("SELECT sku_id FROM skus ORDER BY sku_id").fetchall()]

    # ---- inventory ---- (deterministic spread incl. out-of-stock/low-stock/overstock cases)
    inv_rows = []
    for wi, wh_id in enumerate(wh_ids):
        for si, sku_id in enumerate(sku_ids):
            if (wi + si) % 4 == 3:
                continue  # not every warehouse stocks every sku
            base = 50 + (wi * 17 + si * 11) % 300
            reorder = 40
            max_cap = 400
            qty = base
            if (wi + si) % 9 == 0:
                qty = 0  # out of stock
            elif (wi + si) % 7 == 0:
                qty = 15  # low stock
            elif (wi + si) % 11 == 0:
                qty = 450  # overstock
            expiry = None
            if (wi + si) % 13 == 0:
                expiry = (today - datetime.timedelta(days=5)).isoformat()  # already expired
            bin_code = f"{chr(65 + wi)}{si+1:02d}" if (wi + si) % 15 != 0 else ""  # occasional invalid bin
            inv_rows.append((wh_id, sku_id, qty, reorder, max_cap, bin_code, expiry, now))
    conn.executemany(
        """INSERT INTO inventory (warehouse_id,sku_id,quantity,reorder_level,max_capacity,
                                   location_bin,expiry_date,last_updated) VALUES (?,?,?,?,?,?,?,?)""",
        inv_rows,
    )

    # ---- audits ----
    auditors = ["Sameer Iyer", "Divya Menon", "Arjun Verma"]
    statuses = ["Completed", "In Progress", "Pending"]
    audit_rows = []
    for wi, wh_id in enumerate(wh_ids):
        for k in range(2):
            status = statuses[(wi + k) % 3]
            start = (today - datetime.timedelta(days=20 - (wi + k) * 3)).isoformat()
            end = (today - datetime.timedelta(days=10 - (wi + k))).isoformat() if status == "Completed" else None
            audit_rows.append((wh_id, auditors[(wi + k) % 3], status, start, end))
    conn.executemany(
        "INSERT INTO audits (warehouse_id,auditor_name,status,start_date,end_date) VALUES (?,?,?,?,?)",
        audit_rows,
    )

    # ---- discrepancies ----
    disc_types = ["Quantity Mismatch", "Wrong Location", "Damaged", "Expired", "High Variance"]
    severities = ["High", "Medium", "Low"]
    disc_rows = []
    for wi, wh_id in enumerate(wh_ids):
        for k in range(4):
            sku_id = sku_ids[(wi + k) % len(sku_ids)]
            dtype = disc_types[(wi + k) % len(disc_types)]
            sev = severities[(wi + k) % len(severities)]
            expected = 100 + k * 10
            actual = expected - (15 if dtype == "Quantity Mismatch" else 0)
            detected = (today - datetime.timedelta(days=k * 2)).isoformat()
            disc_rows.append((wh_id, sku_id, dtype, sev, expected, actual, detected))
    conn.executemany(
        """INSERT INTO discrepancies (warehouse_id,sku_id,disc_type,severity,expected_qty,actual_qty,detected_at)
           VALUES (?,?,?,?,?,?,?)""",
        disc_rows,
    )

    conn.commit()
    conn.close()


def build_secondary(path, region_names):
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.executescript(SECONDARY_SCHEMA)
    conn.commit()
    conn.close()


def mirror_region_into_secondary(primary_path, secondary_path, region):
    """Copies the warehouses/skus/inventory belonging to `region` from primary
    into the given secondary store, matching preprocessing.py's sync model."""
    pconn = sqlite3.connect(primary_path)
    pconn.row_factory = sqlite3.Row
    sconn = sqlite3.connect(secondary_path)

    whs = pconn.execute("SELECT * FROM warehouses WHERE region=?", (region,)).fetchall()
    sconn.executemany(
        "INSERT INTO warehouses (warehouse_id,name,region,capacity_units) VALUES (?,?,?,?)",
        [(w["warehouse_id"], w["name"], w["region"], w["capacity_units"]) for w in whs],
    )
    wh_ids = [w["warehouse_id"] for w in whs]

    skus = pconn.execute("SELECT * FROM skus").fetchall()
    sconn.executemany(
        "INSERT INTO skus (sku_id,sku_code,description,unit_price,unit_cost) VALUES (?,?,?,?,?)",
        [(s["sku_id"], s["sku_code"], s["description"], s["unit_price"], s["unit_cost"]) for s in skus],
    )

    if wh_ids:
        placeholders = ",".join("?" * len(wh_ids))
        inv = pconn.execute(f"SELECT * FROM inventory WHERE warehouse_id IN ({placeholders})", wh_ids).fetchall()
        sconn.executemany(
            """INSERT INTO inventory (warehouse_id,sku_id,quantity,reorder_level,max_capacity,
                                       location_bin,expiry_date,last_updated) VALUES (?,?,?,?,?,?,?,?)""",
            [(i["warehouse_id"], i["sku_id"], i["quantity"], i["reorder_level"], i["max_capacity"],
              i["location_bin"], i["expiry_date"], i["last_updated"]) for i in inv],
        )

    sconn.commit()
    sconn.close()
    pconn.close()


def main():
    os.makedirs(os.path.dirname(DB_PATHS["primary"]), exist_ok=True)
    build_primary(DB_PATHS["primary"])
    build_secondary(DB_PATHS["secondary_west"], ["WEST"])
    build_secondary(DB_PATHS["secondary_east"], ["EAST"])
    mirror_region_into_secondary(DB_PATHS["primary"], DB_PATHS["secondary_west"], "WEST")
    mirror_region_into_secondary(DB_PATHS["primary"], DB_PATHS["secondary_east"], "EAST")
    print("Seeded:")
    print(" -", DB_PATHS["primary"])
    print(" -", DB_PATHS["secondary_west"])
    print(" -", DB_PATHS["secondary_east"])
    print("\nDemo logins (username / password) — match the buttons in LoginPage.tsx:")
    print("  admin / admin")
    print("  manager1 / manager1   (West)")
    print("  manager2 / manager2   (East)")
    print("  auditor1 / auditor1   (South)")
    print("  viewer1 / viewer1     (West)")


if __name__ == "__main__":
    main()
