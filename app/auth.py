import base64
import hmac
import hashlib
import json
from app.config import JWT_SECRET
from app.db_utils import get_connection


def _sign(payload: bytes) -> str:
    sig = hmac.new(JWT_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return sig


def create_token(user: dict) -> str:
    payload = json.dumps({"username": user["username"], "role": user["role"], "region": user["region"]}).encode()
    b64 = base64.urlsafe_b64encode(payload).decode()
    sig = _sign(payload)
    return f"{b64}.{sig}"


def verify_token(token: str) -> dict | None:
    try:
        b64, sig = token.split(".")
        payload = base64.urlsafe_b64decode(b64.encode())
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        return json.loads(payload)
    except Exception:
        return None


def authenticate(username: str, password: str) -> dict | None:
    conn = get_connection("primary")
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if not row:
        return None
    if hashlib.sha256(password.encode()).hexdigest() != row["password_hash"]:
        return None
    return dict(row)
