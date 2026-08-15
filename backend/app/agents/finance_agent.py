"""
Finance AI Agent - orchestrates LLM + controlled finance tools.

Architecture:
  User question
  → FinanceAgent.chat()
  → LLM provider (OpenRouter/Ollama/Demo)
  → Tool calls (only FinanceTools methods - no raw SQL)
  → Deterministic database queries
  → Result
  → LLM explanation
  → Response to user
"""
import json
import re
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.tools.finance_tools import FinanceTools
from typing import Optional


def _parse_text_tool_calls(text: str) -> list[dict]:
    """Parse Llama-style <function=name({...})></function> from response content or failed_generation."""
    calls = []
    for m in re.finditer(r'<function=(\w+)\((\{.*?\})\)\s*(?:</function>)?', text, re.DOTALL):
        name, raw = m.group(1), m.group(2)
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            args = {}
        calls.append({
            "id": f"call_{name}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        })
    return calls


SYSTEM_PROMPT = """You are FinPilot AI, an intelligent finance assistant for businesses.

You have access to controlled finance tools that query real financial data from the database.
You MUST use these tools to answer financial questions - never invent or guess financial figures.

Guidelines:
- Always use the appropriate tool before answering financial questions
- Present numbers clearly with proper formatting (e.g., ₹12,45,000)
- Be concise but insightful
- If asked about something outside finance, politely redirect
- Always mention the time period when discussing financial figures
- Highlight important trends or concerns when relevant"""


class DemoFinanceAgent:
    """Rule-based demo agent when no LLM API is configured."""

    PATTERNS = [
        (["revenue", "sales", "income", "turnover"], "get_total_revenue"),
        (["expense", "spending", "cost"], "get_expense_breakdown"),
        (["profit", "net", "margin"], "get_net_profit"),
        (["customer", "client", "top", "best"], "get_top_customers"),
        (["outstanding", "receivable", "owed", "due from"], "get_customer_outstanding"),
        (["overdue", "late", "past due"], "get_overdue_invoices"),
        (["vendor", "supplier", "payable"], "get_vendor_payables"),
        (["inventory", "stock", "product"], "get_inventory_summary"),
        (["summary", "overview", "report", "how are we doing"], "get_financial_summary"),
        (["compare", "vs", "versus", "previous", "last month", "month on month"], "compare_periods"),
    ]

    def respond(self, question: str, tools: FinanceTools, company_id: str) -> tuple[str, list, list]:
        q_lower = question.lower()
        tool_name = "get_financial_summary"

        for keywords, t_name in self.PATTERNS:
            if any(kw in q_lower for kw in keywords):
                tool_name = t_name
                break

        result = tools.call_tool(tool_name, {}, company_id)
        tool_calls = [{"name": tool_name, "args": {}}]
        tool_results = [result]

        response = self._format_response(tool_name, result, question)
        return response, tool_calls, tool_results

    def _fmt(self, amount: float) -> str:
        return f"₹{amount:,.0f}"

    def _format_response(self, tool_name: str, result: dict, question: str) -> str:
        fmt = self._fmt
        if tool_name == "get_total_revenue":
            return f"**Total Revenue** ({result.get('period', 'current month')})\n\n{fmt(result['total_revenue'])}\n\n*This represents all approved sales invoices for the period.*"

        if tool_name == "get_total_expenses":
            return f"**Total Expenses** ({result.get('period', 'current month')})\n\n{fmt(result['total_expenses'])}\n\n*This includes all approved expenses for the period.*"

        if tool_name == "get_net_profit":
            profit = result['net_profit']
            emoji = "📈" if profit > 0 else "📉"
            return (f"{emoji} **Net Profit** ({result.get('period', 'current month')})\n\n"
                    f"- Revenue: {fmt(result['total_revenue'])}\n"
                    f"- Expenses: {fmt(result['total_expenses'])}\n"
                    f"- **Net Profit: {fmt(profit)}**\n"
                    f"- Profit Margin: {result['profit_margin_percent']}%")

        if tool_name == "get_top_customers":
            customers = result.get("top_customers", [])
            lines = [f"**Top Customers by Revenue** ({result.get('period', 'current month')})\n"]
            for c in customers:
                lines.append(f"{c['rank']}. **{c['name']}** — {fmt(c['revenue'])} ({c['invoice_count']} invoices)")
            return "\n".join(lines)

        if tool_name == "get_customer_outstanding":
            customers = result.get("customers_with_outstanding", [])
            if not customers:
                return "✅ **No outstanding receivables.** All invoices are paid!"
            lines = [f"**Outstanding Receivables** — Total: {fmt(result['total_outstanding'])}\n"]
            for c in customers[:8]:
                lines.append(f"- **{c['name']}**: {fmt(c['outstanding'])}")
            return "\n".join(lines)

        if tool_name == "get_overdue_invoices":
            invoices = result.get("overdue_invoices", [])
            if not invoices:
                return "✅ **No overdue invoices.** All invoices are within their due dates."
            lines = [f"**Overdue Invoices** — {result['count']} invoices, {fmt(result['total_overdue'])} total\n"]
            for inv in invoices[:8]:
                lines.append(f"- {inv['invoice_number']}: {fmt(inv['outstanding'])} — {inv['days_overdue']} days overdue")
            return "\n".join(lines)

        if tool_name == "get_expense_breakdown":
            breakdown = result.get("expense_breakdown", [])
            lines = [f"**Expense Breakdown** ({result.get('period', 'current month')}) — Total: {fmt(result['total_expenses'])}\n"]
            for item in breakdown[:8]:
                lines.append(f"- **{item['category']}**: {fmt(item['amount'])} ({item['percentage']}%)")
            return "\n".join(lines)

        if tool_name == "get_vendor_payables":
            vendors = result.get("vendor_payables", [])
            lines = ["**Vendor Purchase Summary**\n"]
            for v in vendors[:8]:
                lines.append(f"- **{v['vendor']}**: {fmt(v['total_purchases'])}")
            return "\n".join(lines)

        if tool_name == "get_inventory_summary":
            r = result
            lines = [
                f"**Inventory Summary**\n",
                f"- Total Products: {r['total_products']}",
                f"- Total Inventory Value: {fmt(r['total_inventory_value'])}",
                f"- Low Stock Items: {r['low_stock_count']}",
            ]
            if r.get("low_stock_products"):
                lines.append("\n**Low Stock Alert:**")
                for p in r["low_stock_products"]:
                    lines.append(f"- {p['name']} (SKU: {p.get('sku', 'N/A')}): {p['stock']} units (threshold: {p['threshold']})")
            return "\n".join(lines)

        if tool_name == "compare_periods":
            r = result
            rev = r["revenue"]
            exp = r["expenses"]

            def change_str(pct):
                if pct is None:
                    return "N/A"
                arrow = "↑" if pct > 0 else "↓"
                return f"{arrow} {abs(pct)}%"

            return (
                f"**Month-over-Month Comparison**\n\n"
                f"**Revenue:**\n"
                f"- Current ({r['current_period']}): {fmt(rev['current'])}\n"
                f"- Previous ({r['previous_period']}): {fmt(rev['previous'])}\n"
                f"- Change: {change_str(rev['change_percent'])}\n\n"
                f"**Expenses:**\n"
                f"- Current: {fmt(exp['current'])}\n"
                f"- Previous: {fmt(exp['previous'])}\n"
                f"- Change: {change_str(exp['change_percent'])}"
            )

        # financial summary
        r = result
        return (
            f"**Financial Summary** ({r.get('period', 'current month')})\n\n"
            f"- 💰 Revenue: {fmt(r['revenue'])}\n"
            f"- 💸 Expenses: {fmt(r['expenses'])}\n"
            f"- 📊 Net Profit: {fmt(r['net_profit'])} ({r['profit_margin']}% margin)\n"
            f"- 📋 Outstanding Receivables: {fmt(r['outstanding_receivables'])}\n"
            f"- ⚠️ Overdue Invoices: {r['overdue_invoices']} ({fmt(r['overdue_amount'])})"
        )


class OpenRouterAgent:
    """Uses OpenRouter API with tool calling."""

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = settings.AI_MODEL
        self.base_url = "https://openrouter.ai/api/v1"

    def chat(self, messages: list, tools: list) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://finpilot.ai",
            "X-Title": "FinPilot AI",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "max_tokens": 1024,
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()


class GroqAgent:
    """Uses Groq API — fast inference, free tier available at console.groq.com."""

    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self.base_url = "https://api.groq.com/openai/v1"

    def chat(self, messages: list, tools: list) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 1024,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)

            # Groq returns 400 tool_use_failed when model outputs <function=...> text format.
            # Rescue the call from failed_generation and return it as a proper tool_calls response.
            if resp.status_code == 400:
                body = resp.json()
                err = body.get("error", {})
                if err.get("code") == "tool_use_failed":
                    failed_gen = err.get("failed_generation", "")
                    parsed = _parse_text_tool_calls(failed_gen)
                    if parsed:
                        return {"choices": [{"message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": parsed,
                        }}]}
                resp.raise_for_status()

            resp.raise_for_status()
            data = resp.json()

            # Also handle text-based <function=...> in content (model didn't use structured calls)
            choice_msg = data["choices"][0]["message"]
            if not choice_msg.get("tool_calls") and choice_msg.get("content"):
                parsed = _parse_text_tool_calls(choice_msg["content"])
                if parsed:
                    choice_msg["tool_calls"] = parsed
                    choice_msg["content"] = None

            return data



class FinanceAgent:
    """Main orchestrator. Routes to the correct provider."""

    def __init__(self, db: Session):
        self.db = db
        self.tools = FinanceTools(db)

    def chat(self, question: str, company_id: str, conversation_history: list = None,
             provider_override: Optional[str] = None) -> dict:
        effective_provider = provider_override or settings.AI_PROVIDER

        tool_defs = self.tools.get_tool_definitions()
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if conversation_history:
            messages.extend(conversation_history[-10:])  # keep last 10 messages for context
        messages.append({"role": "user", "content": question})

        try:
            if effective_provider == "groq":
                provider = GroqAgent()
            else:
                provider = OpenRouterAgent()

            response = provider.chat(messages, tool_defs)
            choice = response["choices"][0]["message"]
            tool_calls_made = []
            tool_results = []

            # Execute tool calls if the model requested them
            if choice.get("tool_calls"):
                for tc in choice["tool_calls"]:
                    fn = tc["function"]
                    args = json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments"), str) else fn.get("arguments", {})
                    result = self.tools.call_tool(fn["name"], args, company_id)
                    tool_calls_made.append({"name": fn["name"], "args": args})
                    tool_results.append(result)

                # Send tool results back to LLM for final response
                messages.append(choice)
                for i, tc in enumerate(choice["tool_calls"]):
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(tool_results[i]),
                    })

                final_response = provider.chat(messages, [])
                final_text = final_response["choices"][0]["message"]["content"]
            else:
                final_text = choice.get("content", "I couldn't process your request. Please try again.")

            return {
                "response": final_text,
                "tool_calls": tool_calls_made,
                "tool_results": tool_results,
                "is_demo": False,
                "provider": effective_provider,
            }

        except Exception as e:
            error_detail = str(e)

            if hasattr(e, 'response') and e.response is not None:
                try:
                    body = e.response.json()
                    error_detail = f"HTTP {e.response.status_code}: {body}"
                except Exception:
                    error_detail = f"HTTP {e.response.status_code}: {e.response.text[:800]}"

            return {
                "response": f"The AI provider **{effective_provider}** returned an error. See the error details below.",
                "tool_calls": [],
                "tool_results": [],
                "is_demo": False,
                "provider": "error",
                "error": error_detail,
            }
