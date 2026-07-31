# Setup & Run

## Backend

```bash
pip install -r requirements.txt         # now includes langgraph
python scripts/init_db.py               # creates + seeds db/*.db (destructive, re-run anytime)
uvicorn app.main:app --reload --port 8000
```

`http://localhost:8000/health` → `{"status": "ok"}`

## Frontend

```bash
cd frontend
npm install
npm run dev                              # http://localhost:5173
```

Login with any of the demo buttons on the login screen (admin / manager1 /
manager2 / auditor1 / viewer1 — passwords match usernames). These are
seeded by `scripts/init_db.py` to match the hardcoded `DEMO_ACCOUNTS` in
`LoginPage.tsx`.

For production, `npm run build` emits `frontend/dist/`, which `app/main.py`
will then serve directly — so you only need to run the FastAPI process.

## What changed in this pass

1. **LangGraph pipeline.** `orchestrator.py`'s manual if/while control flow
   is now `app/agents/graph.py` — a `StateGraph` with one node per pipeline
   stage (intent → cache → text2sql → RBAC gate → execute → mask → answer →
   satisfaction → retry-loop). See `FILE_SCHEMA.md` for the node map and
   which nodes are LLM-backed "agents" vs. deterministic logic. Behavior is
   unchanged — same inputs produce the same outputs, same retry semantics.
2. **Frontend wired up.** Your uploaded pages/components are in place under
   `frontend/src/`; I filled in what was missing to make it buildable
   (`AuthContext.tsx`, `package.json`, Vite/TS config, `index.html`). See
   "Frontend" section in `FILE_SCHEMA.md` for the full list of what I added
   vs. what you provided.
3. **Demo credentials realigned.** Seed data usernames/passwords now match
   `LoginPage.tsx`'s hardcoded demo buttons exactly (previous seed had
   different usernames like `manager_west`; that's fixed).

## Before you go further

1. **Verify the Azure OpenAI key in `.env`.** It had embedded
   spaces/line-breaks when pasted — I stripped whitespace and inserted it,
   but confirm it matches the Azure Portal for `xeroxaiservices-resource`,
   or `/chat` and audit-report calls will 500.
2. **Confirm `AZURE_OPENAI_DEPLOYMENT`.** Set to `gpt-5` as a placeholder —
   replace with your actual deployment *name* from Azure AI Studio.
3. **Rotate the key** — it's been typed into chat, treat it as exposed.
4. Leave `AZURE_OPENAI_API_KEY` blank to run fully offline (deterministic
   stubs for every LLM call) while you wire up the frontend — no cost, no
   quota needed.

## Docs

- `FILE_SCHEMA.md` — module map, the LangGraph pipeline, frontend structure, HTTP route table.
- `DB_SCHEMA.md` — every table/column, the primary/secondary store split, row-level RBAC.

## Sandbox note

Assembled and smoke-tested in an environment without internet access:
auth → RBAC-scoped SQL → masking → answer generation → dashboard metrics all
verified working end-to-end (with `AZURE_OPENAI_API_KEY` unset, exercising
the offline-stub code paths). `langgraph`, `openai`, and `sqlparse` couldn't
be pip-installed here to test the graph invocation, live-LLM, and rule-based
SQL-safety-check paths directly — they're either unchanged from your
original code or straightforward LangGraph API usage, and will run once you
`pip install -r requirements.txt` in your real environment. Similarly,
`npm install && npm run build` for the frontend needs to happen on your end
(no internet in this sandbox to fetch node packages).

## What changed in this round

1. **CSV upload page** (`/app/data-upload`, admin/manager only). A drag-and-drop
   CSV upload that pushes rows straight into the DB — same validation, dedup,
   and primary→secondary sync as the existing simulated ERP push button, just
   fed by a file instead of hand-built JSON. Backend: `POST /ingest/upload-csv`,
   parsed by `preprocessing.parse_csv_records()`, then handed to the *same*
   `process_ingest_push()` the JSON route already used — nothing about the
   original `/ingest/push` route changed.
2. **AI audit insights, extended.**
   - The existing per-warehouse report (`/audit-report/{id}`) now also feeds the
     LLM each warehouse's inventory risk stats (low stock / out of stock /
     overstock / invalid location counts) and returns a `risk_stats` +
     `high_severity_count` field alongside the original response shape.
   - New: `GET /audit-report/consolidated` — one LLM-generated summary across
     every warehouse in the caller's RBAC scope, shown at the top of the Audit
     Reports page, with a per-warehouse discrepancy breakdown underneath.
3. **Role → page access is now explicit and enforced twice.** See
   `FILE_SCHEMA.md`'s "Role → Page Access" table. Sidebar visibility
   (`AppShell.tsx`) and a route guard (`App.tsx`'s `RoleRoute`) both gate
   Data Upload (admin/manager) and Observability (admin); every other page
   is open to any logged-in role, same as before.
4. **Sample CSV datasets.** `scripts/export_sample_data.py` dumps the current
   DB contents (warehouses, skus, inventory, audits, discrepancies, sync_log —
   `users`/`obs_logs` excluded since they carry credentials/PII) to CSV under
   `sample_data/<store>/*.csv`. This is a one-shot snapshot for showing "this
   is the kind of data the system runs on", not a live sync — re-run the
   script any time you want a fresh snapshot.

## Next round

Bring the next batch of files whenever — I'll fold them into this same
structure (backend into `app/` or `app/agents/`, frontend into
`frontend/src/pages` or `components`) rather than starting over.
