"""
In-memory chat cache. If a new question is sufficiently similar (fuzzy
string match on normalized tokens) to a previously answered question by the
SAME role+region scope, we reuse its generated SQL/tag instead of re-running
text-to-SQL, then just re-executes the SQL fresh (so data stays live) and
regenerates the NL answer. This mirrors semantic caching without needing an
embeddings service for the hackathon demo.
"""
from difflib import SequenceMatcher
from app.config import CACHE_SIMILARITY_THRESHOLD

_CACHE: dict[str, dict] = {}  # key: f"{role}:{region}" -> list of {question, sql, intent}


def _normalize(q: str) -> str:
    return " ".join(sorted(q.lower().strip().split()))


def _scope_key(role: str, region: str | None) -> str:
    return f"{role}:{region or 'ALL'}"


def find_similar(question: str, role: str, region: str | None):
    scope = _scope_key(role, region)
    entries = _CACHE.get(scope, [])
    norm_q = _normalize(question)
    best, best_score = None, 0.0
    for e in entries:
        score = SequenceMatcher(None, norm_q, _normalize(e["question"])).ratio()
        if score > best_score:
            best, best_score = e, score
    if best and best_score >= CACHE_SIMILARITY_THRESHOLD:
        return best
    return None


def store(question: str, role: str, region: str | None, sql: str, intent: str):
    scope = _scope_key(role, region)
    _CACHE.setdefault(scope, [])
    _CACHE[scope].append({"question": question, "sql": sql, "intent": intent})
    # keep last 200 per scope
    _CACHE[scope] = _CACHE[scope][-200:]


def stats():
    return {scope: len(v) for scope, v in _CACHE.items()}
