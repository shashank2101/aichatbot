"""
Role-Based Access Control.

Two layers of enforcement, both applied BEFORE anything reaches the LLM:
  1. TABLE-LEVEL: which tables/stores a role+region may query at all.
  2. COLUMN-LEVEL: sensitive columns (price/cost) get stripped from the
     result set for roles that shouldn't see them, before the answer-writer
     LLM ever sees the rows.

Roles: admin, manager, auditor, viewer
"""

ROLES = ["admin", "manager", "auditor", "viewer"]

# Tables every role may see (subject to region routing below).
TABLE_ACCESS = {
    "admin":   {"warehouses", "skus", "inventory", "audits", "discrepancies", "sync_log", "obs_logs", "users"},
    "manager": {"warehouses", "skus", "inventory", "audits", "discrepancies", "sync_log"},
    "auditor": {"warehouses", "skus", "inventory", "audits", "discrepancies"},
    "viewer":  {"warehouses", "skus", "inventory", "audits", "discrepancies"},
}

# Columns hidden from the LLM / final answer for a given role, per table.
COLUMN_MASK = {
    "viewer": {
        "skus": {"unit_price", "unit_cost"},
    },
    "auditor": {
        "skus": {"unit_cost"},   # auditors can see price context but not internal cost
    },
    "manager": {},
    "admin": {},
}

# Regions a role may cross into. admin/manager1(WEST)/manager2(EAST) etc.
# "SOUTH" = primary DB itself (Hyderabad DC), always visible to everyone
# (it's the consolidation warehouse), region restriction applies to the
# SECONDARY stores only.
def allowed_regions(role: str, user_region: str | None):
    if role == "admin":
        return {"SOUTH", "WEST", "EAST", "CENTRAL"}
    if role == "manager":
        return {"SOUTH", user_region}
    # auditor / viewer: primary (SOUTH) + their own home region only
    return {"SOUTH", user_region}


def table_allowed(role: str, table: str) -> bool:
    return table.lower() in TABLE_ACCESS.get(role, set())


def masked_columns(role: str, table: str) -> set:
    return COLUMN_MASK.get(role, {}).get(table.lower(), set())


def denial_message(role: str, table_or_region: str) -> str:
    return (
        f"You don't have access to that data source (`{table_or_region}`) with your current role "
        f"(`{role}`). You can access: warehouses, skus, inventory, audits, and discrepancies data "
        f"for the regions your account is scoped to. Ask your admin for elevated access if you need more."
    )
