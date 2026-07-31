import os
from app.llm import call_llm
from app.db_utils import get_connection

SKILL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "skills", "AUDIT_REPORT_SKILL.md")

_PER_WAREHOUSE_MARKER = "# Consolidated (Multi-Warehouse) Audit Report — System Prompt"


def _load_skill() -> str:
    with open(SKILL_PATH, "r") as f:
        return f.read()


def _per_warehouse_prompt() -> str:
    """Everything above the consolidated section — unchanged behavior for the existing agent."""
    full = _load_skill()
    return full.split(_PER_WAREHOUSE_MARKER)[0].strip()


def _consolidated_prompt() -> str:
    full = _load_skill()
    parts = full.split(_PER_WAREHOUSE_MARKER)
    return (_PER_WAREHOUSE_MARKER + parts[1]).strip() if len(parts) > 1 else full


def _inventory_risk_stats(conn, warehouse_id: int) -> dict:
    """Lightweight per-warehouse inventory risk signals, fed to the LLM alongside
    audits/discrepancies so the summary has more than just the discrepancy table
    to reason about (deeper insight, same response shape as before)."""
    rows = conn.execute("SELECT * FROM inventory WHERE warehouse_id=?", (warehouse_id,)).fetchall()
    low_stock = sum(1 for r in rows if 0 < r["quantity"] < r["reorder_level"])
    out_of_stock = sum(1 for r in rows if r["quantity"] == 0)
    overstock = sum(1 for r in rows if r["quantity"] > r["max_capacity"])
    invalid_location = sum(1 for r in rows if not r["location_bin"] or len(r["location_bin"]) < 3)
    return {
        "sku_lines": len(rows),
        "low_stock_count": low_stock,
        "out_of_stock_count": out_of_stock,
        "overstock_count": overstock,
        "invalid_location_count": invalid_location,
    }


def generate_report(warehouse_id: int, role: str) -> dict:
    conn = get_connection("primary")
    wh = conn.execute("SELECT * FROM warehouses WHERE warehouse_id=?", (warehouse_id,)).fetchone()
    audits = conn.execute("SELECT * FROM audits WHERE warehouse_id=?", (warehouse_id,)).fetchall()
    discs = conn.execute(
        """SELECT d.*, s.sku_code FROM discrepancies d JOIN skus s ON d.sku_id = s.sku_id
           WHERE d.warehouse_id=? ORDER BY CASE severity WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END""",
        (warehouse_id,),
    ).fetchall()

    if not wh:
        conn.close()
        return {"error": "warehouse not found"}

    risk_stats = _inventory_risk_stats(conn, warehouse_id)
    conn.close()

    from app.agents import mask_agent
    disc_rows = mask_agent.mask_rows([dict(d) for d in discs], role)

    high_severity = sum(1 for d in disc_rows if d.get("severity") == "High")

    system_prompt = _per_warehouse_prompt()
    user_prompt = (
        f"Warehouse: {wh['name']} ({wh['region']})\n"
        f"Audits: {[dict(a) for a in audits]}\n"
        f"Discrepancies: {disc_rows}\n"
        f"Inventory risk stats: {risk_stats}"
    )
    text, tokens = call_llm(system_prompt, user_prompt, mode="audit_report")
    return {
        "warehouse": wh["name"],
        "region": wh["region"],
        "summary": text,
        "discrepancy_count": len(disc_rows),
        "high_severity_count": high_severity,
        "risk_stats": risk_stats,
        "tokens_used": tokens,
    }


def generate_consolidated_report(warehouse_ids: list[int] | None, role: str) -> dict:
    """AI insight summary across every warehouse the caller's role/region can see.
    warehouse_ids=None means no restriction (admin/global)."""
    conn = get_connection("primary")
    if warehouse_ids is None:
        wh_rows = conn.execute("SELECT * FROM warehouses").fetchall()
    elif warehouse_ids:
        wh_rows = conn.execute(
            f"SELECT * FROM warehouses WHERE warehouse_id IN ({','.join('?' * len(warehouse_ids))})",
            tuple(warehouse_ids),
        ).fetchall()
    else:
        wh_rows = []

    from app.agents import mask_agent

    per_warehouse = []
    total_audits = total_completed = total_discs = total_high = 0
    for wh in wh_rows:
        wid = wh["warehouse_id"]
        audits = conn.execute("SELECT * FROM audits WHERE warehouse_id=?", (wid,)).fetchall()
        discs = conn.execute(
            """SELECT d.*, s.sku_code FROM discrepancies d JOIN skus s ON d.sku_id = s.sku_id
               WHERE d.warehouse_id=?""",
            (wid,),
        ).fetchall()
        disc_rows = mask_agent.mask_rows([dict(d) for d in discs], role)
        high = sum(1 for d in disc_rows if d.get("severity") == "High")
        completed = sum(1 for a in audits if a["status"] == "Completed")

        total_audits += len(audits)
        total_completed += completed
        total_discs += len(disc_rows)
        total_high += high

        per_warehouse.append({
            "warehouse": wh["name"],
            "region": wh["region"],
            "audits_total": len(audits),
            "audits_completed": completed,
            "discrepancy_count": len(disc_rows),
            "high_severity_count": high,
        })

    conn.close()

    system_prompt = _consolidated_prompt()
    user_prompt = f"Per-warehouse data: {per_warehouse}"
    text, tokens = call_llm(system_prompt, user_prompt, mode="audit_report_consolidated")

    return {
        "summary": text,
        "warehouse_count": len(per_warehouse),
        "total_audits": total_audits,
        "total_audits_completed": total_completed,
        "total_discrepancies": total_discs,
        "total_high_severity": total_high,
        "per_warehouse": sorted(per_warehouse, key=lambda w: -w["discrepancy_count"]),
        "tokens_used": tokens,
    }
