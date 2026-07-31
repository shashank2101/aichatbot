from app.db_utils import get_connection
from app.observability import get_analytics


def _wh_filter_clause(warehouse_ids):
    if not warehouse_ids:
        return ""
    ids = ",".join(str(i) for i in warehouse_ids)
    return f"WHERE warehouse_id IN ({ids})"


def get_dashboard_metrics(warehouse_ids: list[int] | None = None) -> dict:
    """
    warehouse_ids=None -> admin/global view (all warehouses in primary).
    Pass a restricted list to scope the dashboard to a manager/viewer's region.
    """
    conn = get_connection("primary")
    wf = _wh_filter_clause(warehouse_ids)

    total_warehouses = conn.execute(
        f"SELECT COUNT(DISTINCT warehouse_id) c FROM warehouses {wf.replace('warehouse_id','warehouse_id') if wf else ''}"
    ).fetchone()["c"] if not wf else conn.execute(
        f"SELECT COUNT(*) c FROM warehouses WHERE warehouse_id IN ({','.join(str(i) for i in warehouse_ids)})"
    ).fetchone()["c"]

    total_skus = conn.execute("SELECT COUNT(*) c FROM skus").fetchone()["c"]

    inv_rows = conn.execute(f"SELECT * FROM inventory {wf}").fetchall()
    total_units = sum(r["quantity"] for r in inv_rows)
    low_stock = [r for r in inv_rows if 0 < r["quantity"] < r["reorder_level"]]
    out_of_stock = [r for r in inv_rows if r["quantity"] == 0]
    overstock = [r for r in inv_rows if r["quantity"] > r["max_capacity"]]

    # inventory value (join sku price)
    price_map = {r["sku_id"]: r["unit_price"] for r in conn.execute("SELECT sku_id, unit_price FROM skus").fetchall()}
    inventory_value = round(sum((r["quantity"] * price_map.get(r["sku_id"], 0)) for r in inv_rows), 2)

    # duplicate / missing sku checks
    sku_ids_in_inventory = [r["sku_id"] for r in inv_rows]
    valid_sku_ids = {r["sku_id"] for r in conn.execute("SELECT sku_id FROM skus").fetchall()}
    missing_sku = [r for r in inv_rows if r["sku_id"] not in valid_sku_ids]
    seen = {}
    duplicate_sku_rows = []
    for r in inv_rows:
        key = (r["warehouse_id"], r["sku_id"])
        if key in seen:
            duplicate_sku_rows.append(r)
        seen[key] = True
    invalid_location = [r for r in inv_rows if not r["location_bin"] or len(r["location_bin"]) < 3]

    # audits
    audit_wf = wf
    audits = conn.execute(f"SELECT * FROM audits {audit_wf}").fetchall()
    completed = [a for a in audits if a["status"] == "Completed"]
    pending = [a for a in audits if a["status"] == "Pending"]
    in_progress = [a for a in audits if a["status"] == "In Progress"]
    audit_progress_pct = round(100 * len(completed) / len(audits), 1) if audits else 0.0

    # discrepancies
    disc_wf = wf
    discs = conn.execute(f"SELECT * FROM discrepancies {disc_wf}").fetchall()
    shortages = [d for d in discs if d["disc_type"] == "Quantity Mismatch" and d["actual_qty"] < d["expected_qty"]]
    overstock_disc = [d for d in discs if d["disc_type"] == "Quantity Mismatch" and d["actual_qty"] > d["expected_qty"]]
    wrong_location = [d for d in discs if d["disc_type"] == "Wrong Location"]
    damaged = [d for d in discs if d["disc_type"] == "Damaged"]
    expired = [d for d in discs if d["disc_type"] == "Expired"]
    high_variance = [d for d in discs if d["disc_type"] == "High Variance"]
    high_severity = [d for d in discs if d["severity"] == "High"]

    # operational
    wh_rows = conn.execute("SELECT warehouse_id, name, capacity_units FROM warehouses").fetchall()
    wh_cap = {r["warehouse_id"]: (r["name"], r["capacity_units"]) for r in wh_rows}
    util_by_wh = {}
    for r in inv_rows:
        util_by_wh.setdefault(r["warehouse_id"], 0)
        util_by_wh[r["warehouse_id"]] += r["quantity"]
    warehouse_utilization = [
        {
            "warehouse": wh_cap.get(wid, ("?", 1))[0],
            "utilization_pct": round(100 * qty / wh_cap.get(wid, ("?", 1))[1], 1),
        }
        for wid, qty in util_by_wh.items()
    ]

    disc_by_wh = {}
    for d in discs:
        disc_by_wh[d["warehouse_id"]] = disc_by_wh.get(d["warehouse_id"], 0) + 1
    top_disc_wh = None
    if disc_by_wh:
        top_wid = max(disc_by_wh, key=disc_by_wh.get)
        top_disc_wh = {"warehouse": wh_cap.get(top_wid, ("?", 0))[0], "discrepancy_count": disc_by_wh[top_wid]}

    sku_freq = {}
    sku_code_map = {r["sku_id"]: r["sku_code"] for r in conn.execute("SELECT sku_id, sku_code FROM skus").fetchall()}
    for d in discs:
        sku_freq[d["sku_id"]] = sku_freq.get(d["sku_id"], 0) + 1
    freq_skus = sorted(sku_freq.items(), key=lambda x: -x[1])[:5]
    frequently_affected_skus = [{"sku_code": sku_code_map.get(sid, "?"), "count": c} for sid, c in freq_skus]

    conn.close()
    ai_metrics = get_analytics()

    return {
        "inventory": {
            "total_warehouses": total_warehouses,
            "total_skus": total_skus,
            "total_inventory_units": total_units,
            "inventory_value": inventory_value,
            "low_stock_count": len(low_stock),
            "out_of_stock_count": len(out_of_stock),
            "overstock_count": len(overstock),
            "duplicate_sku_count": len(duplicate_sku_rows),
            "missing_sku_count": len(missing_sku),
            "invalid_location_count": len(invalid_location),
        },
        "audit": {
            "audit_progress_pct": audit_progress_pct,
            "completed_audits": len(completed),
            "pending_audits": len(pending),
            "active_audits": len(in_progress),
            "total_audits": len(audits),
        },
        "discrepancy": {
            "total_discrepancies": len(discs),
            "shortages": len(shortages),
            "overstock": len(overstock_disc),
            "wrong_location": len(wrong_location),
            "damaged": len(damaged),
            "expired": len(expired),
            "high_variance": len(high_variance),
            "high_severity": len(high_severity),
        },
        "operational": {
            "warehouse_utilization": warehouse_utilization,
            "top_discrepancy_warehouse": top_disc_wh,
            "frequently_affected_skus": frequently_affected_skus,
        },
        "ai_metrics": {
            "total_questions": ai_metrics["total_questions"],
            "avg_latency_ms": ai_metrics["avg_latency_ms"],
            "avg_tokens_used": ai_metrics["avg_tokens_used"],
            "cache_hit_rate_pct": ai_metrics["cache_hit_rate_pct"],
            "jailbreak_attempts": ai_metrics["jailbreak_attempts"],
            "thumbs_up": ai_metrics["thumbs_up"],
            "thumbs_down": ai_metrics["thumbs_down"],
            "unsatisfied_answers": ai_metrics["unsatisfied_answers"],
        },
    }


def get_alerts(warehouse_ids: list[int] | None = None) -> list[dict]:
    """Deterministic alert feed derived straight from the data (no LLM)."""
    conn = get_connection("primary")
    wf = _wh_filter_clause(warehouse_ids)
    alerts = []

    for r in conn.execute(f"SELECT * FROM inventory {wf}").fetchall():
        if r["quantity"] == 0:
            alerts.append({"severity": "High", "type": "Out of Stock",
                            "message": f"SKU at warehouse {r['warehouse_id']} is out of stock (bin {r['location_bin']})."})
        elif r["quantity"] < r["reorder_level"]:
            alerts.append({"severity": "Medium", "type": "Low Stock",
                            "message": f"SKU at warehouse {r['warehouse_id']} below reorder level ({r['quantity']} < {r['reorder_level']})."})
        if r["expiry_date"]:
            import datetime
            try:
                exp = datetime.date.fromisoformat(r["expiry_date"])
                if exp < datetime.date.today():
                    alerts.append({"severity": "High", "type": "Expired Item",
                                    "message": f"Item in bin {r['location_bin']} at warehouse {r['warehouse_id']} expired on {exp.isoformat()}."})
            except ValueError:
                pass

    disc_wf = wf
    for d in conn.execute(f"SELECT * FROM discrepancies {disc_wf} {'AND' if disc_wf else 'WHERE'} severity='High'").fetchall():
        alerts.append({"severity": "High", "type": d["disc_type"],
                        "message": f"High-severity {d['disc_type']} at warehouse {d['warehouse_id']} (expected {d['expected_qty']}, actual {d['actual_qty']})."})

    conn.close()
    return alerts[:50]
