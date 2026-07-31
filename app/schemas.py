from pydantic import BaseModel, Field
from typing import Optional, Any


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str
    region: Optional[str]
    full_name: str


class ChatRequest(BaseModel):
    question: str
    token: str
    session_id: str = Field(min_length=1, max_length=128)


class ChatResponse(BaseModel):
    answer: str
    sql: Optional[str] = None
    rows: Optional[list[dict]] = None
    intent: str
    cache_hit: bool = False
    retries: int = 0
    log_id: Optional[int] = None
    blocked: bool = False


class FeedbackRequest(BaseModel):
    log_id: int
    thumbs: str  # "up" | "down"


class IngestPayloadItem(BaseModel):
    warehouse_id: int
    sku_code: str
    quantity: int
    location_bin: Optional[str] = None
    source_system: Optional[str] = "ERP"


class IngestPushRequest(BaseModel):
    records: list[IngestPayloadItem]
