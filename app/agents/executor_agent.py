from app.db_utils import run_select, get_connection
from app import rbac
from app.config import REGION_TO_STORE


def stores_for_user(role: str, region: str | None) -> list[str]:
    """
    Determines which physical SQLite DB(s) to query for this user.
    admin -> primary (it already contains the consolidated view of everything)
    manager/auditor/viewer -> primary is always allowed (it's the source-of-truth
    consolidation warehouse), plus their own secondary store if their role/region
    combination permits it, enabling cross joins when the question needs both.
    """
    allowed = rbac.allowed_regions(role, region)
    stores = ["primary"]
    for r in allowed:
        s = REGION_TO_STORE.get(r)
        if s and s != "primary" and s not in stores:
            stores.append(s)
    return stores


def _allowed_warehouse_names(role: str, region: str | None) -> set | None:
    """
    None => no restriction (admin). Otherwise the set of warehouse names this
    user may see. Needed because `primary` physically holds ALL regions' data
    (it's the consolidation store) — table-level RBAC alone isn't enough,
    we also need this row-level filter for non-admin roles.
    """
    if role == "admin":
        return None
    regions = rbac.allowed_regions(role, region)
    conn = get_connection("primary")
    placeholders = ",".join("?" * len(regions))
    rows = conn.execute(f"SELECT name FROM warehouses WHERE region IN ({placeholders})", tuple(regions)).fetchall()
    conn.close()
    return {r["name"] for r in rows}


def execute(sql: str, role: str, region: str | None) -> list[dict]:
    stores = stores_for_user(role, region)
    rows = run_select(sql, stores)

    allowed_names = _allowed_warehouse_names(role, region)
    if allowed_names is None:
        return rows
    # Row-level filter: if a result row carries a 'warehouse' column (nearly
    # all templates alias w.name AS warehouse), drop rows outside scope.
    filtered = [r for r in rows if r.get("warehouse") is None or r.get("warehouse") in allowed_names]
    return filtered
