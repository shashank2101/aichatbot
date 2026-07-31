from fastapi import FastAPI, HTTPException, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Optional

from app.schemas import (LoginRequest, LoginResponse, ChatRequest, ChatResponse,
                          FeedbackRequest, IngestPushRequest)
from app import auth
from app.agents import orchestrator, audit_report_agent
from app import metrics as metrics_mod
from app import observability
from app import preprocessing
from app.db_utils import get_connection
from app.rbac import allowed_regions
from app.config import REGION_TO_STORE

app = FastAPI(title="Conversational Inventory Audit Assistant", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _current_user(authorization: Optional[str]) -> dict:
    if not authorization:
        raise HTTPException(401, "Missing token")
    token = authorization.replace("Bearer ", "")
    user = auth.verify_token(token)
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    return user


def _scoped_warehouse_ids(role: str, region: Optional[str]) -> Optional[list[int]]:
    """None => no restriction (admin/global). Otherwise list of warehouse_ids in scope."""
    if role == "admin":
        return None
    regions = allowed_regions(role, region)
    conn = get_connection("primary")
    rows = conn.execute(
        f"SELECT warehouse_id FROM warehouses WHERE region IN ({','.join('?' * len(regions))})",
        tuple(regions),
    ).fetchall()
    conn.close()
    return [r["warehouse_id"] for r in rows]


# ---------------------------------------------------------------- AUTH
@app.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    user = auth.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(401, "Invalid username or password")
    token = auth.create_token(user)
    return LoginResponse(token=token, username=user["username"], role=user["role"],
                          region=user["region"], full_name=user["full_name"])


# ---------------------------------------------------------------- CHAT
import traceback
from fastapi import HTTPException

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    print("Request received")

    user = auth.verify_token(req.token)
    print("Token verified:", user)

    if not user:
        raise HTTPException(401, "Invalid or expired token")

    try:
        print("Calling orchestrator...")
        result = orchestrator.handle_question(req.question, user)
        print("Orchestrator result:", result)

        return ChatResponse(**result)

    except Exception:
        traceback.print_exc()
        raise

@app.post("/chat/feedback")
def chat_feedback(req: FeedbackRequest, authorization: Optional[str] = Header(None)):
    _current_user(authorization)
    conn = get_connection("primary")
    conn.execute("UPDATE obs_logs SET thumbs=? WHERE id=?", (req.thumbs, req.log_id))
    conn.commit()
    conn.close()
    return {"ok": True}


# ---------------------------------------------------------------- DASHBOARD
@app.get("/dashboard/metrics")
def dashboard_metrics(authorization: Optional[str] = Header(None)):
    user = _current_user(authorization)
    wh_ids = _scoped_warehouse_ids(user["role"], user.get("region"))
    return metrics_mod.get_dashboard_metrics(wh_ids)


@app.get("/alerts")
def alerts(authorization: Optional[str] = Header(None)):
    user = _current_user(authorization)
    wh_ids = _scoped_warehouse_ids(user["role"], user.get("region"))
    return {"alerts": metrics_mod.get_alerts(wh_ids)}


@app.get("/audit-report/consolidated")
def audit_report_consolidated(authorization: Optional[str] = Header(None)):
    user = _current_user(authorization)
    wh_ids = _scoped_warehouse_ids(user["role"], user.get("region"))
    return audit_report_agent.generate_consolidated_report(wh_ids, user["role"])


@app.get("/audit-report/{warehouse_id}")
def audit_report(warehouse_id: int, authorization: Optional[str] = Header(None)):
    user = _current_user(authorization)
    wh_ids = _scoped_warehouse_ids(user["role"], user.get("region"))
    if wh_ids is not None and warehouse_id not in wh_ids:
        raise HTTPException(403, "You don't have access to this warehouse's audit report.")
    return audit_report_agent.generate_report(warehouse_id, user["role"])


# ---------------------------------------------------------------- ADMIN / OBSERVABILITY
@app.get("/admin/observability")
def admin_observability(authorization: Optional[str] = Header(None)):
    user = _current_user(authorization)
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access only.")
    return observability.get_analytics()


# ---------------------------------------------------------------- INGEST (simulated ERP push button)
@app.post("/ingest/push")
def ingest_push(req: IngestPushRequest, authorization: Optional[str] = Header(None)):
    user = _current_user(authorization)
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(403, "Only admin/manager can trigger data sync.")
    records = [r.model_dump() for r in req.records]
    return preprocessing.process_ingest_push(records)


@app.post("/ingest/upload-csv")
async def ingest_upload_csv(file: UploadFile = File(...), authorization: Optional[str] = Header(None)):
    user = _current_user(authorization)
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(403, "Only admin/manager can trigger data sync.")
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file.")

    content = await file.read()
    records, parse_errors = preprocessing.parse_csv_records(content)
    result = preprocessing.process_ingest_push(records) if records else {
        "accepted": 0, "rejected": 0, "rejected_details": [], "synced_to_secondary": {},
    }
    result["parse_errors"] = parse_errors
    result["filename"] = file.filename
    return result


# ---------------------------------------------------------------- MISC
@app.get("/me")
def me(authorization: Optional[str] = Header(None)):
    return _current_user(authorization)


@app.get("/warehouses")
def list_warehouses(authorization: Optional[str] = Header(None)):
    user = _current_user(authorization)
    wh_ids = _scoped_warehouse_ids(user["role"], user.get("region"))
    conn = get_connection("primary")
    if wh_ids is None:
        rows = conn.execute("SELECT * FROM warehouses").fetchall()
    else:
        rows = conn.execute(
            f"SELECT * FROM warehouses WHERE warehouse_id IN ({','.join('?' * len(wh_ids))})", tuple(wh_ids)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------- FRONTEND (Vite build)
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    def serve_root():
        return FileResponse(_FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        """Serve static files or index.html for client-side routes."""
        file = _FRONTEND_DIST / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(_FRONTEND_DIST / "index.html")
