from app.llm import call_llm

SYSTEM_PROMPT = """You judge whether an answer fully addresses the user's question,
given the data it was based on. Respond with exactly one word: SATISFIED or INSUFFICIENT."""


def is_satisfied(question: str, answer: str, row_count: int) -> tuple[bool, int]:
    # cheap deterministic guard first: empty rows + vague answer = clearly insufficient
    if row_count == 0 and len(answer) < 40:
        return False, 0

    user_prompt = f"Question: {question}\nAnswer given: {answer}\nRows returned: {row_count}"
    verdict, tokens = call_llm(SYSTEM_PROMPT, user_prompt,mode="satisfaction")
    satisfied = "SATISFIED" in verdict.upper() and "INSUFFICIENT" not in verdict.upper()
    return satisfied, tokens
