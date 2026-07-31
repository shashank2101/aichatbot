from app.llm import call_llm

SYSTEM_PROMPT = """You are an inventory audit assistant. Generate a concise, natural-language
answer to the user's question using ONLY the provided data rows. Do not invent numbers.
If the data is empty, say clearly that no matching records were found.
Keep it under 120 words, use bullet points for lists of more than 3 items."""


def generate_answer(question: str, rows: list[dict]) -> tuple[str, int]:
    if not rows:
        return "No matching records were found for that question.", 0
    preview = rows[:25]
    user_prompt = f"Question: {question}\n\nData ({len(rows)} rows, showing up to 25):\n{preview}"
    text, tokens = call_llm(SYSTEM_PROMPT, user_prompt, mode="answer")

    # offline fallback needs *some* real signal, not just a generic stub
    if text == "__USE_DETERMINISTIC_SUMMARY__":
        text = _offline_summarize(question, rows)
    return text, tokens


def _offline_summarize(question: str, rows: list[dict]) -> str:
    n = len(rows)
    cols = list(rows[0].keys())
    lines = [f"Found {n} matching record(s)."]
    for r in rows[:8]:
        parts = [f"{c}: {r[c]}" for c in cols if r[c] is not None][:5]
        lines.append("- " + ", ".join(parts))
    if n > 8:
        lines.append(f"...and {n - 8} more.")
    return "\n".join(lines)
