"""
OrderAgent — handles sales and purchase order queries.

Responsibilities:
- Sales order list and status
- Purchase order list and status
- Order fulfilment status

Note: Orders are local-only in FinPilot. TallyPrime order sync requires TDL configuration
which is not included in the standard connector. Orders are tracked in FinPilot for reference.

Tools available: No dedicated order read tools yet (orders are accessed via the REST API).
This agent answers general questions about order workflow.
"""

ORDERS_SYSTEM = """You are FinPilot's Order Management Agent.

You answer questions about:
- Sales orders (from customers) and their status
- Purchase orders (to vendors) and their status
- Order fulfilment workflow

Important note to users:
FinPilot stores orders locally. TallyPrime does not have a standard order sync API in the
connector's current implementation. Orders created in FinPilot are tracked here for reference
and can be converted to invoices manually. If you need Tally order sync, it requires TDL.

For order data, direct users to the Orders section in the navigation.
Be honest about what you can and cannot look up — without a dedicated order query tool,
you cannot retrieve specific order counts or values in this conversation."""

ORDERS_TOOL_NAMES: set = set()   # No read tools yet — orders answered conversationally


class OrderAgent:
    """Handles order management questions."""

    system_prompt = ORDERS_SYSTEM
    tool_names = ORDERS_TOOL_NAMES
    domain = "orders"

    def describe(self) -> str:
        return "Order specialist: sales orders, purchase orders, fulfilment status (local-only)"
