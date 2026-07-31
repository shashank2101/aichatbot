"""
The /chat pipeline as a LangGraph StateGraph, replacing the manual
if/while control flow that used to live in orchestrator.py. Behavior is
unchanged — this is a structural refactor, not a logic change.

Node map (see FILE_SCHEMA.md for the full pipeline description):

  classify_intent  deterministic  intent_agent.classify_intent (regex/keyword) — node
                                renamed from "intent" to avoid colliding with the
                                GraphState "intent" field (newer langgraph rejects
                                a node id that matches a state key)
  jailbreak     deterministic  terminal — refusal message
  off_topic     deterministic  terminal — deflection message
  greeting      deterministic  terminal — canned greeting
  cache         deterministic  cache.find_similar (fuzzy match, no LLM)
  text2sql      >>> AGENT <<<  text2sql_agent.generate_sql — hits the LLM
                                when config.USE_LLM=True, else rule templates
  no_sql        deterministic  terminal — "couldn't translate that" message
  table_gate    deterministic  rbac.table_allowed via mask_agent
  execute       deterministic  runs SQL against the right store(s) + row RBAC
  mask          deterministic  strips sensitive columns before the LLM sees rows
  generate_answer >>> AGENT <<< answer_agent.generate_answer — hits the LLM
                                (renamed from "answer" for the same reason as
                                classify_intent above)
  satisfaction  >>> AGENT <<<  satisfaction_agent.is_satisfied — hits the LLM
  retry         >>> AGENT <<<  re-generates SQL with a nudged prompt, loops to execute
  finalize      deterministic  terminal — marks a normal completion

Retry loop: satisfaction -> retry -> execute -> mask -> answer -> satisfaction,
up to config.MAX_SATISFACTION_RETRIES times, exactly matching the original
while-loop semantics.
"""
from typing import TypedDict, Optional, Any
from langgraph.graph import StateGraph, END

from app.agents import intent_agent, text2sql_agent, mask_agent, executor_agent, answer_agent, satisfaction_agent
from app import cache
from app.config import MAX_SATISFACTION_RETRIES


class GraphState(TypedDict, total=False):
    question: str
    role: str
    region: Optional[str]
    username: str
    chat_history: list[dict[str, str]]

    intent: str
    sql: Optional[str]
    cache_hit: bool
    rows: list[dict[str, Any]]
    masked_rows: list[dict[str, Any]]
    answer: str
    satisfied: bool
    retries: int
    total_tokens: int
    blocked: bool
    error: Optional[str]
    exit_reason: str  # jailbreak | off_topic | greeting | no_sql | denied | error | completed


# ---------------------------------------------------------------- nodes
def intent_node(state: GraphState) -> dict:
    intent, tokens = intent_agent.classify_intent(state["question"])

    return {
        "intent": intent,
        "total_tokens": state.get("total_tokens", 0) + tokens,
    }

def jailbreak_node(_state: GraphState) -> dict:
    return {"answer": intent_agent.JAILBREAK_REPLY, "blocked": True, "exit_reason": "jailbreak"}


def off_topic_node(_state: GraphState) -> dict:
    return {"answer": intent_agent.OFF_TOPIC_REPLY, "blocked": True, "exit_reason": "off_topic"}


def greeting_node(_state: GraphState) -> dict:
    return {
        "answer": "Hi! I can help with inventory levels, stock, audits, and discrepancies. What would you like to know?",
        "blocked": False,
        "exit_reason": "greeting",
    }


def cache_node(state: GraphState) -> dict:
    cached = cache.find_similar(state["question"], state["role"], state["region"])
    if cached:
        return {"sql": cached["sql"], "cache_hit": True}
    return {"cache_hit": False}


def text2sql_node(state: GraphState) -> dict:
    """AGENT NODE — calls out to the LLM (or rule-based fallback) via text2sql_agent."""
    if state.get("sql"):
        return {}  # cache already supplied SQL, nothing to generate
    stores = executor_agent.stores_for_user(state["role"], state["region"])
    sql, tok = text2sql_agent.generate_sql(state["question"], state["intent"], stores)
    return {"sql": sql, "total_tokens": state.get("total_tokens", 0) + tok}


def no_sql_node(_state: GraphState) -> dict:
    return {
        "answer": "I understood the topic but couldn't translate it into a data query. "
                  "Could you rephrase with more specifics (e.g. warehouse name, SKU, or audit status)?",
        "blocked": False,
        "exit_reason": "no_sql",
    }


def table_gate_node(state: GraphState) -> dict:
    allowed, denial = mask_agent.check_table_access(state["sql"], state["role"])
    if not allowed:
        return {"blocked": True, "answer": denial, "exit_reason": "denied"}
    return {"blocked": False}


def execute_node(state: GraphState) -> dict:
    try:
        rows = executor_agent.execute(state["sql"], state["role"], state["region"])
        return {"rows": rows, "error": None}
    except Exception as e:  # noqa: BLE001 — mirrors original orchestrator's broad catch
        return {
            "rows": [],
            "error": type(e).__name__,
            "answer": f"I hit an error running that query against the database ({type(e).__name__}). Try rephrasing.",
            "exit_reason": "error",
        }


def mask_node(state: GraphState) -> dict:
    return {"masked_rows": mask_agent.mask_rows(state["rows"], state["role"])}


def answer_node(state: GraphState) -> dict:
    """AGENT NODE — calls out to the LLM (or offline stub) via answer_agent."""
    answer, tok = answer_agent.generate_answer(
        state["question"], state["masked_rows"], state.get("chat_history", [])
    )
    return {"answer": answer, "total_tokens": state.get("total_tokens", 0) + tok}


def satisfaction_node(state: GraphState) -> dict:
    """AGENT NODE — calls out to the LLM (or offline stub) via satisfaction_agent."""
    satisfied, tok = satisfaction_agent.is_satisfied(state["question"], state["answer"], len(state["rows"]))
    return {"satisfied": satisfied, "total_tokens": state.get("total_tokens", 0) + tok}


def retry_node(state: GraphState) -> dict:
    """AGENT NODE — regenerates SQL with a nudged prompt before looping back to execute."""
    stores = executor_agent.stores_for_user(state["role"], state["region"])
    sql2, tok = text2sql_agent.generate_sql(
        state["question"] + " (give more complete detail)", state["intent"], stores
    )
    updates = {"retries": state.get("retries", 0) + 1, "total_tokens": state.get("total_tokens", 0) + tok}
    if sql2:
        updates["sql"] = sql2
    return updates


def finalize_node(_state: GraphState) -> dict:
    return {"exit_reason": "completed"}


# ---------------------------------------------------------------- routing

def route_after_intent(state: GraphState) -> str:
    intent = state["intent"]
    if intent == "jailbreak_attempt":
        return "jailbreak"
    if intent == "off_topic":
        return "off_topic"
    if intent == "greeting":
        return "greeting"
    return "cache"


def route_after_text2sql(state: GraphState) -> str:
    return "table_gate" if state.get("sql") else "no_sql"


def route_after_gate(state: GraphState) -> str:
    return "denied" if state.get("blocked") else "execute"


def route_after_execute(state: GraphState) -> str:
    return "error" if state.get("error") else "mask"


def route_after_satisfaction(state: GraphState) -> str:
    if state.get("satisfied") or state.get("retries", 0) >= MAX_SATISFACTION_RETRIES:
        return "done"
    return "retry"


# ---------------------------------------------------------------- build

def build_graph():
    g = StateGraph(GraphState)

    g.add_node("classify_intent", intent_node)
    g.add_node("jailbreak", jailbreak_node)
    g.add_node("off_topic", off_topic_node)
    g.add_node("greeting", greeting_node)
    g.add_node("cache", cache_node)
    g.add_node("text2sql", text2sql_node)
    g.add_node("no_sql", no_sql_node)
    g.add_node("table_gate", table_gate_node)
    g.add_node("execute", execute_node)
    g.add_node("mask", mask_node)
    g.add_node("generate_answer", answer_node)
    g.add_node("satisfaction", satisfaction_node)
    g.add_node("retry", retry_node)
    g.add_node("finalize", finalize_node)

    g.set_entry_point("classify_intent")
    g.add_conditional_edges(
        "classify_intent", route_after_intent,
        {"jailbreak": "jailbreak", "off_topic": "off_topic", "greeting": "greeting", "cache": "cache"},
    )
    g.add_edge("jailbreak", END)
    g.add_edge("off_topic", END)
    g.add_edge("greeting", END)

    g.add_edge("cache", "text2sql")
    g.add_conditional_edges("text2sql", route_after_text2sql, {"table_gate": "table_gate", "no_sql": "no_sql"})
    g.add_edge("no_sql", END)

    g.add_conditional_edges("table_gate", route_after_gate, {"denied": END, "execute": "execute"})
    g.add_conditional_edges("execute", route_after_execute, {"error": END, "mask": "mask"})

    g.add_edge("mask", "generate_answer")
    g.add_edge("generate_answer", "satisfaction")
    g.add_conditional_edges("satisfaction", route_after_satisfaction, {"done": "finalize", "retry": "retry"})
    g.add_edge("retry", "execute")
    g.add_edge("finalize", END)

    return g.compile()


# Compiled once at import time and reused across requests (cheap — no I/O
# happens until .invoke() is called with real state).
GRAPH = build_graph()
