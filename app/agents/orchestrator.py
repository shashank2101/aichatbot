"""
Public entry point for the /chat pipeline. The actual step-by-step logic now
lives in app/agents/graph.py as a LangGraph StateGraph (see that file for the
node-by-node breakdown). This module just: builds the initial state, invokes
the compiled graph, and translates the final state into the response shape
`main.py` / `schemas.ChatResponse` expects — plus the observability logging
and cache-store side effects that depend on *which* exit path was taken.
"""
import time
import datetime

from app.agents.graph import GRAPH
from app import cache
from app.db_utils import get_chat_history, log_event, save_chat_message
from app.config import MAX_SATISFACTION_RETRIES


def handle_question(question: str, user: dict, session_id: str) -> dict:
    """user = {"username", "role", "region"}"""
    t0 = time.time()
    role, region, username = user["role"], user.get("region"), user["username"]
    history = get_chat_history(session_id, username)
    save_chat_message(session_id, username, "user", question)

    initial_state = {
        "question": question,
        "role": role,
        "region": region,
        "username": username,
        "retries": 0,
        "total_tokens": 0,
        "cache_hit": False,
        "rows": [],
        "sql": None,
        "chat_history": history,
    }
    state = GRAPH.invoke(initial_state)

    exit_reason = state.get("exit_reason")
    intent = state["intent"]
    total_tokens = state.get("total_tokens", 0)
    sql = state.get("sql")
    rows = state.get("rows", [])
    answer = state.get("answer", "")
    cache_hit = state.get("cache_hit", False)
    retries = state.get("retries", 0)

    if exit_reason == "jailbreak":
        _log(username, question, intent, None, False, True, t0, 0, None, 0)
        return _save_assistant_response(session_id, username, _resp(answer, intent, blocked=True))

    if exit_reason == "off_topic":
        _log(username, question, intent, None, False, False, t0, 0, None, 0)
        return _save_assistant_response(session_id, username, _resp(answer, intent, blocked=True))

    if exit_reason == "greeting":
        _log(username, question, intent, None, False, False, t0, 0, None, 0)
        return _save_assistant_response(session_id, username, _resp(answer, intent))

    if exit_reason == "no_sql":
        _log(username, question, intent, None, cache_hit, False, t0, total_tokens, None, 0, satisfied=0)
        return _save_assistant_response(session_id, username, _resp(answer, intent, cache_hit=cache_hit))

    if exit_reason == "denied":
        _log(username, question, intent, sql, cache_hit, False, t0, total_tokens, None, 0, satisfied=0)
        return _save_assistant_response(session_id, username, _resp(answer, intent, sql=sql, blocked=True))

    # exit_reason in ("error", "completed") -- both log + cache the same way,
    # matching the original orchestrator's fall-through behavior.
    if not cache_hit and sql:
        cache.store(question, role, region, sql, intent)

    log_id = _log(username, question, intent, sql, cache_hit, False, t0, total_tokens, None, retries,
                   satisfied=1 if retries < MAX_SATISFACTION_RETRIES else 0)

    return _save_assistant_response(
        session_id,
        username,
        _resp(answer, intent, sql=sql, rows=rows[:50], cache_hit=cache_hit, retries=retries, log_id=log_id),
    )


def _resp(answer, intent, sql=None, rows=None, cache_hit=False, retries=0, log_id=None, blocked=False):
    return {
        "answer": answer, "intent": intent, "sql": sql, "rows": rows,
        "cache_hit": cache_hit, "retries": retries, "log_id": log_id, "blocked": blocked,
    }


def _save_assistant_response(session_id: str, username: str, response: dict) -> dict:
    save_chat_message(session_id, username, "assistant", response["answer"])
    return response


def _log(username, question, intent, sql, cache_hit, jailbreak, t0, tokens, thumbs, retries, satisfied=None):
    latency_ms = int((time.time() - t0) * 1000)
    payload = {
        "username": username,
        "question": question,
        "intent": intent,
        "generated_sql": sql,
        "cache_hit": 1 if cache_hit else 0,
        "jailbreak_flag": 1 if jailbreak else 0,
        "latency_ms": latency_ms,
        "tokens_used": tokens,
        "thumbs": thumbs,
        "satisfied": satisfied,
        "retries": retries,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    log_event(payload)
    from app.db_utils import get_connection
    conn = get_connection("primary")
    row = conn.execute("SELECT MAX(id) id FROM obs_logs").fetchone()
    conn.close()
    return row["id"] if row else None
