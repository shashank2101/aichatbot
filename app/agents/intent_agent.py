import re
from app.llm import call_llm

JAILBREAK_PATTERNS = [
    r"ignore (all|any|previous|the) instructions",
    r"disregard (all|any|previous|the) (rules|instructions|prompt)",
    r"system prompt",
    r"you are now",
    r"act as (an?|the)? ?(unfiltered|jailbroken|dan)",
    r"reveal your (prompt|instructions|rules)",
    r"bypass (rbac|access control|restrictions|security)",
    r"pretend (you|to) (have|are) admin",
    r"drop table",
    r"delete from",
    r"; ?--",
    r"union select",
]

GREETINGS = [
    "hi",
    "hello",
    "hey",
    "good morning",
    "good evening",
    "thanks",
    "thank you",
]

VALID_INTENTS = {
    "off_topic",
    "greeting",
    "dashboard_metrics",
    "audit_query",
    "discrepancy_query",
    "inventory_query",
}

INTENT_SYSTEM_PROMPT = """
You are an intent classifier for an Inventory Audit Assistant.

Your job is to classify the user's query into EXACTLY ONE of the following labels.

Labels:

- greeting
  Greetings or thanks only.

- dashboard_metrics
  Requests for summaries, KPIs, dashboards, metrics, reports or business overviews.

- audit_query
  Questions about audits, audit status, cycle counts, audit history, audit completion.

- discrepancy_query
  Questions about discrepancies, mismatches, damaged items, expired items, shrinkage, variance.

- inventory_query
  Questions about inventory, stock, SKUs, warehouses, quantities, locations, bins, vendors,
  reorder levels, replenishment, capacity, utilization, logistics, inventory value, inventory reports,
  warehouse operations, stock movement or anything reasonably related to inventory.

- off_topic
  ONLY if the question is clearly unrelated to inventory or warehouse operations
  (weather, sports, movies, politics, recipes, jokes, general knowledge, etc.)

Rules:

- If there is ANY reasonable possibility the question is about inventory,
  warehouses, stock, logistics or audits, DO NOT classify it as off_topic.

- Always choose exactly one label.

Return ONLY the label.
"""


def check_jailbreak(question: str) -> bool:
    q = question.lower()
    return any(re.search(pattern, q) for pattern in JAILBREAK_PATTERNS)


def _parse_llm_label(text: str) -> str | None:
    if not text:
        return None

    label = text.strip().lower().strip(".,!?\"'` \n")

    for candidate in VALID_INTENTS:
        if candidate == label:
            return candidate

    for candidate in VALID_INTENTS:
        if candidate in label:
            return candidate

    return None


def classify_intent(question: str) -> tuple[str, int]:
    """
    Returns:
        (intent, tokens_used)
    """

    q = question.lower().strip()

    # Greeting fast-path
    if any(q == g or q.startswith(g) for g in GREETINGS) and len(q.split()) <= 4:
        return "greeting", 0

    # Jailbreak fast-path
    if check_jailbreak(question):
        return "jailbreak_attempt", 0

    # Let the LLM decide everything else
    text, tokens = call_llm(
        INTENT_SYSTEM_PROMPT,
        question,
        mode="intent",
    )

    print("Intent LLM Output:", repr(text))

    label = _parse_llm_label(text)

    print("Parsed Intent:", label)

    if label is None:
        print("LLM returned an invalid label. Falling back to off_topic.")
        return "off_topic", tokens

    return label, tokens


OFF_TOPIC_REPLY = (
    "I'm the Inventory Audit Assistant. I can help with inventory, stock levels, "
    "warehouses, audits, discrepancies, and related analytics. "
    "Your question appears to be outside that scope."
)


JAILBREAK_REPLY = (
    "I can't do that. I'm limited to inventory and audit-related tasks and cannot "
    "override my instructions or your access permissions."
)