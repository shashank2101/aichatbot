# Roles, Metrics & Data Flow — Internal Reference

One place that explains, end to end: who can do what, where every number on
screen comes from, and how a request actually moves through the system.
Pairs with `DB_SCHEMA.md` (tables/columns) and `FILE_SCHEMA.md` (file/route map).

---

## 1. Roles

Four roles, defined in `app/rbac.py`, assigned per-user in the `users` table.

| Role | Region | What it is |
|---|---|---|
| `admin` | none (global) | Full access to every warehouse, every table, unmasked columns |
| `manager` | one region (WEST/EAST/CENTRAL) | Full table access, scoped to their region + the SOUTH consolidation store |
| `auditor` | one region | Same table access as manager, minus `unit_cost` on SKUs |
| `viewer` | one region | Read-only, minus `unit_cost` AND `unit_price` on SKUs |

`SOUTH` (the Hyderabad primary DC) is visible to everyone — it's the
consolidation warehouse, not a region a user is fenced out of.

### 1.1 Table-level access (`rbac.TABLE_ACCESS`)

| Table | admin | manager | auditor | viewer |
|---|---|---|---|---|
| warehouses / skus / inventory / audits / discrepancies | ✔ | ✔ | ✔ | ✔ |
| sync_log | ✔ | ✔ | — | — |
| obs_logs | ✔ | — | — | — |
| users | ✔ | — | — | — |

Enforced in `mask_agent.check_table_access()` — runs after SQL is generated,
before it's executed. If the generated SQL touches a table the role can't
see, execution is blocked outright and the user gets a denial message.

### 1.2 Column-level masking (`rbac.COLUMN_MASK`)

| Role | Masked columns |
|---|---|
| viewer | `skus.unit_price`, `skus.unit_cost` |
| auditor | `skus.unit_cost` |
| manager, admin | none |

Enforced in `mask_agent.mask_rows()` — runs after execution, before the row
data is ever handed to the answer-writing LLM. The LLM never sees a masked
column, so it can't leak it in prose either.

### 1.3 Row-level access (why it's not just table + column)

`primary.db` physically contains every region's data (it's the consolidation
store), so table/column rules alone would let a `manager` in WEST read EAST's
warehouse rows straight out of `primary`. `executor_agent._allowed_warehouse_names()`
closes that: after a query runs, any result row carrying a `warehouse` column
gets dropped if that warehouse's region isn't in the caller's
`rbac.allowed_regions()`. This is why almost every generated SQL template
aliases the warehouse name as `warehouse` — it's the hook this filter keys off.

### 1.4 Role → Page access (frontend)

| Page | Route | admin | manager | auditor | viewer |
|---|---|---|---|---|---|
| Chat | `/app/chat` | ✔ | ✔ | ✔ | ✔ |
| Dashboard | `/app/dashboard` | ✔ | ✔ | ✔ | ✔ |
| Alerts | `/app/alerts` | ✔ | ✔ | ✔ | ✔ |
| Audit Reports | `/app/audit-reports` | ✔ | ✔ | ✔ | ✔ |
| Data Upload | `/app/data-upload` | ✔ | ✔ | — | — |
| Observability | `/app/observability` | ✔ | — | — | — |

Gated twice: `AppShell.tsx` hides the sidebar link, and `App.tsx`'s
`RoleRoute` redirects away if the role doesn't match — so typing the URL
directly doesn't bypass anything. The *real* boundary is server-side: every
route in `app/main.py` re-checks the role independently (`/ingest/*` checks
`admin`/`manager`, `/admin/observability` checks `admin`) — the frontend
gating is UX, not the security layer.

Every page is additionally scoped by region for non-admin roles via
`_scoped_warehouse_ids()` in `main.py`, which every metrics/alerts/report
endpoint calls before touching data.

---

## 2. Where each metric comes from

Everything on the **Dashboard** page comes from one call: `GET /dashboard/metrics`
→ `metrics.get_dashboard_metrics(warehouse_ids)`. It's pure SQL aggregation,
no LLM involved. `warehouse_ids` is the caller's RBAC-scoped list from
`_scoped_warehouse_ids()` (or `None` for admin = unrestricted).

| Metric group | Source table(s) | How it's computed |
|---|---|---|
| Total warehouses / SKUs | `warehouses`, `skus` | `COUNT(*)`, scoped by warehouse_ids |
| Inventory units / value | `inventory` × `skus.unit_price` | `SUM(quantity)`, `SUM(qty × price)` |
| Low stock / out of stock / overstock | `inventory` | `quantity` vs `reorder_level` / `max_capacity` |
| Duplicate / missing SKU / invalid location | `inventory` | dedup key check, FK check, `location_bin` length check |
| Audit progress % | `audits` | `Completed / total`, scoped |
| Discrepancy breakdown | `discrepancies` | grouped by `disc_type` / `severity` |
| Warehouse utilization | `inventory` + `warehouses.capacity_units` | `SUM(quantity) / capacity_units` per warehouse |
| Top discrepancy warehouse, frequent SKUs | `discrepancies` | `MAX`/`GROUP BY` |
| `ai_metrics` block | `obs_logs` (via `observability.get_analytics()`) | see §4 below |

**Auto-refresh:** the Dashboard page polls this endpoint every **10 seconds**
(`REFRESH_INTERVAL_MS` in `DashboardPage.tsx`) so the numbers stay current
without a manual reload. The first load blocks on a loading state; every
refresh after that is silent — the page keeps showing the last-known-good
numbers while it fetches, and only swaps them in once the new response
lands. A small badge next to the title shows a live pulse indicator, the
exact `Last updated <time>` timestamp, and a manual refresh button.

**Alerts** (`GET /alerts` → `metrics.get_alerts()`) are also pure SQL/Python —
out-of-stock, low-stock, expired, and high-severity-discrepancy rows,
re-derived fresh on every call, no LLM, no caching.

---

## 3. Chat — how a question becomes an answer

`POST /chat` is the only endpoint that touches an LLM for arbitrary natural
language. It's a LangGraph `StateGraph` (`app/agents/graph.py`); every box
below is a node:

```
question
   │
   ▼
intent classify  (regex fast-path for greetings/jailbreaks, else LLM label)
   │
   ├─ greeting / off_topic / jailbreak → canned reply, END
   │
   ▼
cache lookup     (fuzzy-match against past questions in the SAME role:region
                   scope — reuses prior SQL if similar enough, else miss)
   │
   ▼
text-to-SQL      ← THIS is the "chat about anything" step
   │
   ▼
RBAC table gate  → SQL touches a forbidden table? blocked, denial message
   │
   ▼
execute          → runs against the right store(s), then row-level RBAC filter
   │
   ▼
column mask      → strips unit_cost/unit_price per role, BEFORE the LLM sees rows
   │
   ▼
answer generation (LLM writes NL prose from the masked rows only)
   │
   ▼
satisfaction check → if the answer looks thin, loop back to text-to-SQL with
   │                   a nudged prompt (up to 2 retries), else finish
   ▼
log to obs_logs, cache the SQL for reuse, return to frontend
```

### 3.1 Text-to-SQL is genuinely dynamic, not a fixed menu

`text2sql_agent.generate_sql()` has two paths:

- **Live LLM mode** (`AZURE_OPENAI_API_KEY` set — this is the current
  `.env` state): the question, plus the *actual* schema of whichever
  store(s) the caller's role can see (`db_utils.get_schema_text()`), is sent
  straight to the model with instructions to write one safe `SELECT`. This
  is not limited to the four intent buckets — the model can join any table
  it's allowed to see, filter on any column, aggregate however the question
  asks. Intent classification (§3.2) is only used for routing (off-topic /
  greeting / jailbreak / cache scoping), not to restrict what SQL can be
  written.
- **Offline rule-based fallback** (no API key configured): a set of
  keyword-matched SQL templates per intent, so the demo still runs without
  any cost/quota. This pass also closed a gap here — `dashboard_metrics`
  questions ("give me an overview", "how are we doing") previously had no
  template and dead-ended into "couldn't translate that question"; there's
  now a portfolio-rollup template for that intent too, so every intent
  bucket has offline coverage.

Every candidate SQL string — LLM-written or template — is passed through
`is_safe_select()` before it's ever run: must parse as exactly one
`SELECT` statement, no `INSERT/UPDATE/DELETE/DROP/ALTER/ATTACH/PRAGMA`, no
stacked statements.

### 3.2 What intent classification actually gates

`intent_agent.classify_intent()` picks one of: `greeting`, `jailbreak_attempt`,
`off_topic`, `dashboard_metrics`, `audit_query`, `discrepancy_query`,
`inventory_query`. It decides:

- Whether to short-circuit with a canned reply (greeting/off-topic/jailbreak)
- Which cache scope to check (`cache.py` keys on `role:region`, not on intent)
- Which offline template bucket to use, if running without live LLM

It does **not** restrict which tables/columns the SQL can touch — that's
RBAC's job (§1.1–1.3), enforced independently after the SQL exists,
regardless of how it was generated.

---

## 4. Observability — where `ai_metrics` and the Observability page come from

Every `/chat` call writes exactly one row to `obs_logs` (username, question,
intent, generated_sql, cache_hit, jailbreak_flag, latency_ms, tokens_used,
thumbs, satisfied, retries). `observability.get_analytics()` aggregates that
table — average latency/tokens, cache hit rate, jailbreak count, thumbs
up/down, unsatisfied-answer count, top questions, recent failures. This
powers both the Dashboard's `ai_metrics` block and the standalone
Observability page (admin-only, `GET /admin/observability`).

---

## 5. Data ingest — two front doors, one pipeline

Both the original JSON push and the new CSV upload funnel into the exact
same validation/sync logic — `preprocessing.process_ingest_push()` — so
there's one place that owns "what counts as a valid inventory record."

```
JSON body  ──┐
             ├─► process_ingest_push()
CSV file   ──┘        │
 (parsed by            ├─ dedupe within the batch (warehouse_id, sku_code)
  parse_csv_records)    ├─ type coercion + required-field check
                         ├─ validate warehouse_id exists
                         ├─ validate sku_code format + exists in skus
                         ├─ upsert into primary.inventory
                         ├─ write a sync_log row (ERP/CSV → primary)
                         └─ push the same row into the correct secondary
                            store (secondary_west / secondary_east) based
                            on the warehouse's region, + its own sync_log row
```

- `POST /ingest/push` — JSON body, admin/manager only (unchanged from before).
- `POST /ingest/upload-csv` — multipart CSV file, admin/manager only (new).
  Required columns: `warehouse_id, sku_code, quantity`. Optional:
  `location_bin, source_system`. Rows that fail to parse are reported
  separately (`parse_errors`) from rows that parse but fail validation
  (`rejected_details`), so the UI can show a bad-CSV-structure error
  differently from a bad-data error.

Neither path can create a new warehouse or SKU — both are look-ups against
existing master data (`warehouses`, `skus`), by design: this is an
inventory-quantity sync, not a master-data editor.

---

## 6. AI audit insights — two levels

`app/agents/audit_report_agent.py`, driven by `skills/AUDIT_REPORT_SKILL.md`
(one file, two prompt sections — split on a marker string so both stay in
sync with the same house style/rules).

- **Per-warehouse** (`GET /audit-report/{warehouse_id}`): audits +
  discrepancies (RBAC column-masked) + inventory risk stats (low stock/out
  of stock/overstock/invalid-location counts for that warehouse) go to the
  LLM together. Returns `summary`, `discrepancy_count`, `high_severity_count`,
  `risk_stats`.
- **Consolidated** (`GET /audit-report/consolidated`, new): every warehouse
  in the caller's RBAC scope gets summarized into one per-warehouse stats
  block (audits total/completed, discrepancy count, high-severity count),
  which goes to the LLM as a single portfolio-level prompt. Returns
  `summary` plus the raw per-warehouse breakdown so the UI can render both
  the prose and a sortable list without a second round trip.

Both fall back to a deterministic offline stub (`app/llm.py::_offline_stub`)
when no Azure key is configured, keyed by `mode` (`audit_report` /
`audit_report_consolidated`), same pattern as chat's answer/satisfaction
stubs.

---

## 7. Serving frontend + backend as one process

`app/main.py` mounts `frontend/dist` (the Vite production build) directly:

```bash
cd frontend && npm install && npm run build   # emits frontend/dist/
cd ..
uvicorn app.main:app --port 8000              # serves API *and* UI on :8000
```

If `frontend/dist/` exists, FastAPI serves its static assets under `/assets`,
serves `index.html` at `/`, and catch-all routes fall back to `index.html`
for React Router's client-side routes (`/app/chat`, `/app/dashboard`, etc.) —
so a full page refresh on a deep link still resolves correctly instead of
404ing. This was already true before this pass; nothing about it changed —
noted here since it answers "how do I host this as one thing": build once,
then just run the FastAPI process.

Without a `frontend/dist/` folder present, FastAPI only serves the API
routes — that's the `npm run dev` / `uvicorn --reload` two-process local dev
setup described in `README.md`.
