"""
FinPilot AI — Single ReAct agent (replaces supervisor + domain-agent pattern).

Why faster:
  Old path: supervisor LLM call → domain LLM call (2 round-trips minimum)
  New path: one LLM call → tools → final response (1-2 round-trips)

query_database gives the LLM complete read access with enforced guardrails,
so it can answer any question rather than being limited to pre-coded tools.
"""
import json
import logging
from typing import Optional

from app.core.config import settings
from app.tools.finance_tools import DB_SCHEMA

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 4

# ── Status labels shown in the UI while tools are executing ──────────────────
_TOOL_LABELS: dict[str, str] = {
    "get_total_revenue":       "Calculating revenue…",
    "get_total_expenses":      "Calculating expenses…",
    "get_net_profit":          "Computing profit & loss…",
    "get_top_customers":       "Finding top customers…",
    "get_customer_outstanding":"Checking receivables…",
    "get_overdue_invoices":    "Checking overdue invoices…",
    "get_expense_breakdown":   "Analysing expense categories…",
    "get_vendor_payables":     "Checking vendor payables…",
    "get_inventory_summary":   "Checking inventory…",
    "get_financial_summary":   "Fetching financial summary…",
    "compare_periods":         "Comparing month-on-month…",
    "query_database":          "Querying database…",
    "get_ledgers":             "Fetching ledger data…",
    "get_stock_items":         "Fetching stock items…",
    "get_customers":           "Fetching customers…",
    "get_vendors":             "Fetching vendors…",
    "get_tally_status":        "Checking TallyPrime status…",
    "get_sync_jobs":           "Fetching sync activity…",
    "get_stock_groups":        "Fetching stock groups…",
    "get_units":               "Fetching units…",
    "get_godowns":             "Fetching godowns…",
}

SYSTEM_PROMPT = f"""You are FinPilot AI, a senior financial analyst for Indian SMBs using TallyPrime.

You have COMPLETE READ access to this company's financial database through your tools.
Always call the most appropriate tool before answering any factual question. Never fabricate figures.

Tool selection:
• Standard KPIs (revenue, expenses, profit, receivables, outstanding) → use the named tool — it's faster
• Complex, ad-hoc, specific, or multi-table questions → use query_database with precise PostgreSQL SELECT

Formatting rules:
• Indian currency notation:  ₹12,34,567  (not ₹1,234,567)
• Always state the time period when quoting financial figures
• Be concise, insightful, and proactively highlight anomalies or trends
• If asked to create, update, or delete anything: explain you are read-only via this assistant

{DB_SCHEMA}"""


def _build_tools(ft, mt, tt) -> tuple[list, dict]:
    """Merge tool definitions and handler map from all three tool sources."""
    defs: list = []
    handlers: dict = {}
    for src in (ft, mt, tt):
        for td in src.get_tool_definitions():
            name = td["function"]["name"]
            defs.append(td)
            handlers[name] = src
    return defs, handlers


def run_tool_loop(
    query: str,
    company_id: str,
    provider: str,
    history: list,
) -> dict:
    """
    Synchronous ReAct tool loop — safe to run in a thread-pool executor.

    Creates its own DB session so the request's FastAPI session is not
    shared across threads.

    Returns
    -------
    {
        messages:        list   — full OpenAI-format conversation
        tool_calls:      list   — [{name, args, label}, …]
        tool_results:    list   — [result_dict, …]
        direct_response: str    — LLM's final text (stream word-by-word in the endpoint)
        is_demo:         bool
        error:           str | None
    }
    """
    from app.db.base import SessionLocal
    from app.tools.finance_tools import FinanceTools
    from app.ai.tools.master_tools import MasterTools
    from app.ai.tools.tally_tools import TallyTools
    from app.agents.finance_agent import GroqAgent, OpenRouterAgent, DemoFinanceAgent

    db = SessionLocal()
    try:
        ft = FinanceTools(db)
        mt = MasterTools(db)
        tt = TallyTools(db)

        api_key = settings.GROQ_API_KEY if provider == "groq" else settings.OPENROUTER_API_KEY

        # ── Demo / no-key fallback ────────────────────────────────────────────
        if not api_key or getattr(settings, "is_demo_mode", False):
            demo = DemoFinanceAgent()
            resp, tc, tr = demo.respond(query, ft, company_id)
            return {
                "messages": [],
                "tool_calls": [
                    {"name": c["name"], "args": c.get("args", {}),
                     "label": _TOOL_LABELS.get(c["name"], c["name"])}
                    for c in tc
                ],
                "tool_results": tr,
                "direct_response": resp,
                "is_demo": True,
                "error": None,
            }

        tool_defs, handler_map = _build_tools(ft, mt, tt)
        llm = GroqAgent() if provider == "groq" else OpenRouterAgent()

        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            messages.extend(history[-12:])
        messages.append({"role": "user", "content": query})

        all_tool_calls: list[dict] = []
        all_tool_results: list[dict] = []

        for iteration in range(MAX_TOOL_ITERATIONS):
            try:
                response = llm.chat(messages, tool_defs)
            except Exception as exc:
                logger.error("LLM call failed (iter %d): %s", iteration, exc)
                err = str(exc)
                if hasattr(exc, "response") and exc.response is not None:
                    try:
                        err = f"HTTP {exc.response.status_code}: {exc.response.json()}"
                    except Exception:
                        err = f"HTTP {exc.response.status_code}: {exc.response.text[:300]}"
                return {
                    "messages": messages,
                    "tool_calls": all_tool_calls,
                    "tool_results": all_tool_results,
                    "direct_response": f"The AI provider returned an error: {err}",
                    "is_demo": False,
                    "error": err,
                }

            choice = response["choices"][0]["message"]

            if not choice.get("tool_calls"):
                # LLM responded directly — this is the final answer
                return {
                    "messages": messages,
                    "tool_calls": all_tool_calls,
                    "tool_results": all_tool_results,
                    "direct_response": choice.get("content") or "",
                    "is_demo": False,
                    "error": None,
                }

            # ── Execute tool calls ────────────────────────────────────────────
            messages.append(choice)

            for tc in choice["tool_calls"]:
                fn = tc["function"]
                tool_name = fn["name"]

                try:
                    raw_args = fn.get("arguments", "{}")
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except (json.JSONDecodeError, TypeError):
                    args = {}

                handler = handler_map.get(tool_name)
                try:
                    result = (
                        handler.call_tool(tool_name, args, company_id)
                        if handler
                        else {"error": f"Unknown tool: {tool_name}"}
                    )
                except Exception as exc:
                    result = {"error": f"Tool execution error: {exc}"}

                all_tool_calls.append({
                    "name": tool_name,
                    "args": args,
                    "label": _TOOL_LABELS.get(tool_name, tool_name.replace("_", " ").title() + "…"),
                })
                all_tool_results.append(result)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result),
                })

        # ── Max iterations reached — make one final response-only call ────────
        try:
            final = llm.chat(messages, [])
            final_text = final["choices"][0]["message"].get("content") or ""
        except Exception as exc:
            final_text = f"I gathered the data but hit an error generating the summary: {exc}"

        return {
            "messages": messages,
            "tool_calls": all_tool_calls,
            "tool_results": all_tool_results,
            "direct_response": final_text,
            "is_demo": False,
            "error": None,
        }

    finally:
        db.close()
