"""
Thin LLM wrapper. If Azure OpenAI credentials are configured (see config.py),
real calls are made via the Responses-compatible Chat Completions API.
Otherwise every call falls back to a deterministic stub so the whole pipeline
(and the hackathon demo) still works with zero API keys.

Token usage is estimated (len(text)//4) when running in offline/stub mode,
and read from the real API usage object when live.
"""
from app.config import USE_LLM, AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, \
    AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_VERSION

_client = None
if USE_LLM:
    from openai import AzureOpenAI
    _client = AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_version=AZURE_OPENAI_API_VERSION,
    )


def call_llm(system_prompt: str, user_prompt: str, mode: str = "generic") -> tuple[str, int]:
    """Returns (text, tokens_used).

    `mode` picks which deterministic offline stub to use when no LLM key is
    configured. One of: "answer", "satisfaction", "audit_report", "sql", "generic".
    Callers pass this explicitly rather than relying on prompt-text sniffing,
    which is fragile to prompt wording/line-wrap changes.
    """
    if _client is not None:
        resp = _client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = resp.choices[0].message.content or ""
        tokens = getattr(resp.usage, "total_tokens", 0) if resp.usage else 0
        return text.strip(), tokens

    # ---- OFFLINE FALLBACK (no API key configured) ----
    # Deterministic stub so the demo still runs end-to-end. Real deployments
    # simply set AZURE_OPENAI_API_KEY / ENDPOINT env vars to go live.
    stub = _offline_stub(mode)
    est_tokens = (len(system_prompt) + len(user_prompt) + len(stub)) // 4
    return stub, est_tokens


def _offline_stub(mode: str) -> str:
    if mode == "answer":
        return "__USE_DETERMINISTIC_SUMMARY__"
    if mode == "satisfaction":
        return "SATISFIED"
    if mode == "audit_report":
        return "Audit Summary: several quantity mismatches and high-severity discrepancies were detected. Recommend prioritizing high-severity items for recount."
    if mode == "audit_report_consolidated":
        return ("Consolidated Audit Summary: audit completion and discrepancy patterns vary across "
                "warehouses, with high-severity items concentrated in a subset of locations. "
                "Recommend prioritizing recounts at the highest-discrepancy warehouses and closing "
                "out pending audits before the next cycle.")
    return "OK"
