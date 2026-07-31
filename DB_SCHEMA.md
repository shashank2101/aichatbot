# Database Schema

The app uses **3 separate SQLite files**, not one DB with a region column —
this is the core design decision everything else routes around.

```
db/
  primary.db          # "SOUTH" region (Hyderabad DC) + consolidated warehouse table for ALL regions
  secondary_west.db    # live operational copy for WEST region warehouses only
  secondary_east.db    # live operational copy for EAST region warehouses only
```

`primary.db` is the **source-of-truth consolidation store**: it holds the
`warehouses` and `skus` master tables for every region, plus a full copy of
`inventory`/`audits`/`discrepancies` for all warehouses. The secondary DBs
hold a *regional slice* — a live mirror of just their region's data, used so
region-scoped queries don't have to hit the (larger) primary store, and so
`preprocessing.py`'s ERP-sync pushes land in the right physical location.
`app/config.py:REGION_TO_STORE` is the routing table between region ↔ store.

---

## Tables (primary.db)

### `users`
| column | type | notes |
|---|---|---|
| user_id | INTEGER PK | |
| username | TEXT UNIQUE | |
| password_hash | TEXT | SHA-256 hex digest, see `auth.py` |
| role | TEXT | `admin` \| `manager` \| `auditor` \| `viewer` |
| region | TEXT / NULL | `WEST` \| `EAST` \| `CENTRAL` \| `SOUTH`; NULL for admin (global) |
| full_name | TEXT | |

### `warehouses`
| column | type | notes |
|---|---|---|
| warehouse_id | INTEGER PK | |
| name | TEXT | |
| region | TEXT | `SOUTH` \| `WEST` \| `EAST` \| `CENTRAL` |
| capacity_units | INTEGER | used for utilization % in `metrics.py` |

### `skus`
| column | type | notes |
|---|---|---|
| sku_id | INTEGER PK | |
| sku_code | TEXT UNIQUE | format `SKU-####`, validated by `preprocessing.SKU_RE` |
| description | TEXT | |
| unit_price | REAL | **masked from `viewer` role** |
| unit_cost | REAL | **masked from `viewer` and `auditor` roles** (see `rbac.COLUMN_MASK`) |

### `inventory`
| column | type | notes |
|---|---|---|
| inv_id | INTEGER PK | |
| warehouse_id | INTEGER FK → warehouses | |
| sku_id | INTEGER FK → skus | |
| quantity | INTEGER | `0` = out of stock; `< reorder_level` = low stock; `> max_capacity` = overstock |
| reorder_level | INTEGER | |
| max_capacity | INTEGER | |
| location_bin | TEXT | empty/short (<3 chars) flagged as "invalid location" in dashboard metrics |
| expiry_date | TEXT / NULL | ISO date; past-dated rows surface in `/alerts` |
| last_updated | TEXT | ISO timestamp, bumped by `preprocessing.process_ingest_push` |

### `audits`
| column | type | notes |
|---|---|---|
| audit_id | INTEGER PK | |
| warehouse_id | INTEGER FK → warehouses | |
| auditor_name | TEXT | |
| status | TEXT | `Pending` \| `In Progress` \| `Completed` |
| start_date | TEXT | ISO date |
| end_date | TEXT / NULL | set only when Completed |

### `discrepancies`
| column | type | notes |
|---|---|---|
| disc_id | INTEGER PK | |
| warehouse_id | INTEGER FK → warehouses | |
| sku_id | INTEGER FK → skus | |
| disc_type | TEXT | `Quantity Mismatch` \| `Wrong Location` \| `Damaged` \| `Expired` \| `High Variance` |
| severity | TEXT | `High` \| `Medium` \| `Low` — audit reports sort High first |
| expected_qty | INTEGER | |
| actual_qty | INTEGER | |
| detected_at | TEXT | ISO date |

### `sync_log`
| column | type | notes |
|---|---|---|
| sync_id | INTEGER PK | |
| source_db / target_db | TEXT | e.g. `ERP` → `primary`, or `primary` → `secondary_west` |
| record_type | TEXT | currently always `inventory` |
| record_id | INTEGER | the sku_id touched |
| synced_at | TEXT | |
| status | TEXT | `SUCCESS` |

### `obs_logs`
Every `/chat` call writes one row here — this is what powers `/admin/observability`
and the `ai_metrics` block of `/dashboard/metrics`.

| column | notes |
|---|---|
| username, question, intent | what was asked and how it was classified |
| generated_sql | NULL if intent was off-topic/greeting/jailbreak/untranslatable |
| cache_hit | 1 if served from `cache.py`'s in-memory semantic cache |
| jailbreak_flag | 1 if `intent_agent` flagged a prompt-injection attempt |
| latency_ms, tokens_used | perf/cost tracking |
| thumbs | `up` \| `down` \| NULL, set via `/chat/feedback` |
| satisfied | 0/1 from `satisfaction_agent`'s verdict |
| retries | how many text2sql/answer regeneration loops it took |

---

## Secondary stores (secondary_west.db / secondary_east.db)

Same `warehouses`, `skus`, `inventory`, `sync_log` tables, but only rows for
that region's warehouses. **No `audits`, `discrepancies`, `users`, or
`obs_logs`** — those only ever live on primary, since audit/discrepancy
tracking and observability are consolidation-only concerns per the design.

`db_utils.get_connection_multi()` can `ATTACH` a secondary store onto a
primary connection (aliased `db_secondary_west` / `db_secondary_east`) so a
single query can cross-join both when a question needs region comparison
(e.g. "compare discrepancies East vs West" — note: discrepancies only exist
on primary, so such a query actually reads it from there, not the attached DB).

---

## Row-level RBAC (why `_allowed_warehouse_names` exists)

Table-level RBAC (`rbac.TABLE_ACCESS`) only stops a role from touching a
table it shouldn't. It does **not** stop a `manager_west` user from reading
another region's rows out of `primary.warehouses`, because primary
physically contains everyone's data. `executor_agent._allowed_warehouse_names()`
closes that gap: after execution, any result row carrying a `warehouse`
column gets dropped if that warehouse's region isn't in the caller's
`rbac.allowed_regions()`.

## Seeding

`scripts/init_db.py` creates and seeds all 3 files from scratch (drops
existing tables first — **destructive**, don't run against a live demo you
care about). Demo accounts it creates:

| username | password | role | region |
|---|---|---|---|
| admin | admin123 | admin | (global) |
| manager_west | manager123 | manager | WEST |
| manager_east | manager123 | manager | EAST |
| auditor_east | auditor123 | auditor | EAST |
| viewer_west | viewer123 | viewer | WEST |
