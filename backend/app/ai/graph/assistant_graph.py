"""
LangGraph-based AI Assistant orchestration.

Architecture:
  User query
    → supervisor_node  (SupervisorAgent classifies intent)
    → domain_node      (specialized agent with domain-specific system prompt + tools)
    → END

Each domain node uses its agent's system_prompt and tool_names to scope the LLM call.
Tools are called through approved FinanceTools / MasterTools / TallyTools.
No arbitrary SQL. No direct Tally XML. RBAC is enforced at the API layer before this graph runs.
"""
import json
import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from app.ai.graph.state import AssistantState
from app.ai.agents.supervisor import SupervisorAgent
from app.ai.agents.accounting import AccountingAgent
from app.ai.agents.inventory import InventoryAgent
from app.ai.agents.reporting import ReportingAgent
from app.ai.agents.tally import TallyAgent
from app.ai.agents.parties import PartyAgent
from app.ai.agents.orders import OrderAgent
from app.ai.agents.create import CreateAgent
from app.tools.finance_tools import FinanceTools
from app.ai.tools.master_tools import MasterTools
from app.ai.tools.tally_tools import TallyTools
from app.agents.finance_agent import GroqAgent, OpenRouterAgent, DemoFinanceAgent
from app.core.config import settings

logger = logging.getLogger(__name__)

_SUPERVISOR = SupervisorAgent()
_ACCOUNTING = AccountingAgent()
_INVENTORY = InventoryAgent()
_REPORTING = ReportingAgent()
_TALLY = TallyAgent()
_PARTIES = PartyAgent()
_ORDERS = OrderAgent()
_CREATE = CreateAgent()

_INTENT_TO_AGENT = {
    "accounting": _ACCOUNTING,
    "inventory":  _INVENTORY,
    "reporting":  _REPORTING,
    "tally":      _TALLY,
    "parties":    _PARTIES,
    "orders":     _ORDERS,
    "create":     _CREATE,
    "general":    _REPORTING,   # fall back to reporting for generic finance questions
}

GENERAL_SYSTEM = """You are FinPilot AI, an intelligent finance and accounting assistant for businesses using TallyPrime.

You have access to controlled tools that query real financial data from the database.
ALWAYS use the appropriate tool before answering any factual question about data.
Present numbers in Indian currency format (₹12,45,000). Be concise but insightful.
Never fabricate figures — if data is unavailable, say so explicitly."""


def _get_llm(provider: str):
    if provider == "groq":
        return GroqAgent()
    return OpenRouterAgent()


def supervisor_node(state: AssistantState) -> dict:
    intent = _SUPERVISOR.classify(state["query"], state["provider"])
    return {"intent": intent}


def _build_tool_defs_and_map(
    agent,
    finance_tools: FinanceTools,
    master_tools: MasterTools,
    tally_tools: TallyTools,
) -> tuple[list, dict]:
    """Return (tool_definitions_list, {tool_name: tool_object}) for a given agent."""
    tool_defs = []
    tool_obj_map: dict[str, object] = {}

    wanted = agent.tool_names

    # Reporting / general finance tools
    reporting_names = {td["function"]["name"] for td in finance_tools.get_tool_definitions()}
    if wanted & reporting_names or not wanted:  # empty = use defaults
        for td in finance_tools.get_tool_definitions():
            if not wanted or td["function"]["name"] in wanted:
                tool_defs.append(td)
                tool_obj_map[td["function"]["name"]] = finance_tools

    # Master tools (ledgers, stock items, customers, vendors, etc.)
    master_defs = master_tools.get_tool_definitions()
    for td in master_defs:
        name = td["function"]["name"]
        if name in wanted or not wanted:
            tool_defs.append(td)
            tool_obj_map[name] = master_tools

    # Tally tools
    tally_defs = tally_tools.get_tool_definitions()
    for td in tally_defs:
        name = td["function"]["name"]
        if name in wanted or not wanted:
            tool_defs.append(td)
            tool_obj_map[name] = tally_tools

    return tool_defs, tool_obj_map


def _run_domain_llm(
    state: AssistantState,
    agent,
    finance_tools: FinanceTools,
    master_tools: MasterTools,
    tally_tools: TallyTools,
) -> dict:
    provider = state["provider"]
    api_key = settings.GROQ_API_KEY if provider == "groq" else settings.OPENROUTER_API_KEY

    tool_defs, tool_obj_map = _build_tool_defs_and_map(agent, finance_tools, master_tools, tally_tools)
    system_prompt = getattr(agent, "system_prompt", GENERAL_SYSTEM)

    messages = [{"role": "system", "content": system_prompt}]
    if state.get("messages"):
        messages.extend(state["messages"][-8:])
    messages.append({"role": "user", "content": state["query"]})

    if not api_key or settings.is_demo_mode:
        demo = DemoFinanceAgent()
        resp, tc, tr = demo.respond(state["query"], finance_tools, state["company_id"])
        return {"final_response": resp, "tool_calls": tc, "tool_results": tr, "is_demo": True}

    try:
        llm = _get_llm(provider)
        response = llm.chat(messages, tool_defs)
        choice = response["choices"][0]["message"]
        tool_calls_made = []
        tool_results = []

        if choice.get("tool_calls"):
            for tc in choice["tool_calls"]:
                fn = tc["function"]
                args = json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments"), str) else fn.get("arguments", {})
                tool_name = fn["name"]
                handler = tool_obj_map.get(tool_name)
                if handler:
                    result = handler.call_tool(tool_name, args, state["company_id"])
                else:
                    result = {"error": f"No handler registered for tool: {tool_name}"}
                tool_calls_made.append({"name": tool_name, "args": args})
                tool_results.append(result)

            messages.append(choice)
            for i, tc in enumerate(choice["tool_calls"]):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(tool_results[i]),
                })
            final_resp = llm.chat(messages, [])
            final_text = final_resp["choices"][0]["message"]["content"]
        else:
            final_text = choice.get("content") or "I couldn't process your request. Please try again."

        return {
            "final_response": final_text,
            "tool_calls": tool_calls_made,
            "tool_results": tool_results,
            "is_demo": False,
        }

    except Exception as e:
        logger.error("Domain LLM failed (intent=%s): %s", getattr(agent, "domain", "?"), e)
        err = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                err = f"HTTP {e.response.status_code}: {e.response.json()}"
            except Exception:
                err = f"HTTP {e.response.status_code}: {e.response.text[:400]}"
        return {
            "final_response": f"The AI provider returned an error. Details: {err}",
            "tool_calls": [],
            "tool_results": [],
            "is_demo": False,
            "error": err,
        }


def make_agent_node(agent, finance_tools, master_tools, tally_tools):
    def node(state: AssistantState) -> dict:
        return _run_domain_llm(state, agent, finance_tools, master_tools, tally_tools)
    node.__name__ = f"{getattr(agent, 'domain', 'unknown')}_node"
    return node


def route_from_supervisor(state: AssistantState) -> Literal[
    "accounting_node", "inventory_node", "reporting_node",
    "tally_node", "parties_node", "orders_node", "create_node", "general_node"
]:
    intent_map = {
        "accounting": "accounting_node",
        "inventory":  "inventory_node",
        "reporting":  "reporting_node",
        "tally":      "tally_node",
        "parties":    "parties_node",
        "orders":     "orders_node",
        "create":     "create_node",
    }
    return intent_map.get(state.get("intent", "general"), "general_node")


def build_assistant_graph(
    finance_tools: FinanceTools,
    master_tools: MasterTools,
    tally_tools: TallyTools,
):
    graph = StateGraph(AssistantState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("accounting_node", make_agent_node(_ACCOUNTING, finance_tools, master_tools, tally_tools))
    graph.add_node("inventory_node",  make_agent_node(_INVENTORY, finance_tools, master_tools, tally_tools))
    graph.add_node("reporting_node",  make_agent_node(_REPORTING, finance_tools, master_tools, tally_tools))
    graph.add_node("tally_node",      make_agent_node(_TALLY, finance_tools, master_tools, tally_tools))
    graph.add_node("parties_node",    make_agent_node(_PARTIES, finance_tools, master_tools, tally_tools))
    graph.add_node("orders_node",     make_agent_node(_ORDERS, finance_tools, master_tools, tally_tools))
    graph.add_node("create_node",     make_agent_node(_CREATE, finance_tools, master_tools, tally_tools))
    graph.add_node("general_node",    make_agent_node(_REPORTING, finance_tools, master_tools, tally_tools))

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges("supervisor", route_from_supervisor)

    for node_name in (
        "accounting_node", "inventory_node", "reporting_node", "tally_node",
        "parties_node", "orders_node", "create_node", "general_node",
    ):
        graph.add_edge(node_name, END)

    return graph.compile()


def run_assistant(
    query: str,
    company_id: str,
    user_id: str,
    role: str,
    provider: str,
    conversation_history: list,
    finance_tools: FinanceTools,
    master_tools: MasterTools,
    tally_tools: TallyTools,
) -> dict:
    graph = build_assistant_graph(finance_tools, master_tools, tally_tools)

    initial_state: AssistantState = {
        "user_id": user_id,
        "company_id": company_id,
        "role": role,
        "provider": provider,
        "messages": conversation_history or [],
        "query": query,
        "intent": None,
        "tool_calls": [],
        "tool_results": [],
        "final_response": None,
        "is_demo": False,
        "error": None,
    }

    result = graph.invoke(initial_state)
    return {
        "response": result.get("final_response") or "I couldn't process your request.",
        "tool_calls": result.get("tool_calls", []),
        "tool_results": result.get("tool_results", []),
        "is_demo": result.get("is_demo", False),
        "provider": provider,
        "intent": result.get("intent"),
        "error": result.get("error"),
    }
