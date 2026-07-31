from app.db_utils import get_connection


def get_analytics(limit_faq: int = 10) -> dict:
    conn = get_connection("primary")

    total = conn.execute("SELECT COUNT(*) c FROM obs_logs").fetchone()["c"]
    avg_latency = conn.execute("SELECT AVG(latency_ms) a FROM obs_logs").fetchone()["a"] or 0
    avg_tokens = conn.execute("SELECT AVG(tokens_used) a FROM obs_logs").fetchone()["a"] or 0
    cache_hit_rate = conn.execute(
        "SELECT AVG(cache_hit) a FROM obs_logs"
    ).fetchone()["a"] or 0
    jailbreak_count = conn.execute(
        "SELECT COUNT(*) c FROM obs_logs WHERE jailbreak_flag = 1"
    ).fetchone()["c"]
    thumbs_up = conn.execute("SELECT COUNT(*) c FROM obs_logs WHERE thumbs='up'").fetchone()["c"]
    thumbs_down = conn.execute("SELECT COUNT(*) c FROM obs_logs WHERE thumbs='down'").fetchone()["c"]
    unsatisfied = conn.execute("SELECT COUNT(*) c FROM obs_logs WHERE satisfied = 0").fetchone()["c"]

    faqs = conn.execute(
        """SELECT question, COUNT(*) c FROM obs_logs
           GROUP BY LOWER(TRIM(question)) ORDER BY c DESC LIMIT ?""",
        (limit_faq,),
    ).fetchall()

    failures = conn.execute(
        """SELECT username, question, intent, created_at FROM obs_logs
           WHERE satisfied = 0 OR generated_sql IS NULL
           ORDER BY created_at DESC LIMIT 15"""
    ).fetchall()

    jailbreaks = conn.execute(
        """SELECT username, question, created_at FROM obs_logs
           WHERE jailbreak_flag = 1 ORDER BY created_at DESC LIMIT 15"""
    ).fetchall()

    recent = conn.execute(
        """SELECT id, username, question, intent, cache_hit, latency_ms, tokens_used,
                  thumbs, satisfied, retries, jailbreak_flag, created_at
           FROM obs_logs ORDER BY created_at DESC LIMIT 30"""
    ).fetchall()

    conn.close()
    return {
        "total_questions": total,
        "avg_latency_ms": round(avg_latency, 1),
        "avg_tokens_used": round(avg_tokens, 1),
        "cache_hit_rate_pct": round(cache_hit_rate * 100, 1),
        "jailbreak_attempts": jailbreak_count,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "unsatisfied_answers": unsatisfied,
        "top_questions": [dict(r) for r in faqs],
        "recent_failures": [dict(r) for r in failures],
        "jailbreak_events": [dict(r) for r in jailbreaks],
        "recent_activity": [dict(r) for r in recent],
    }
