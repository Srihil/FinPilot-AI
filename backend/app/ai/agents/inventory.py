"""
InventoryAgent — handles inventory-domain queries.

Responsibilities:
- Stock item queries (list, search, balances, low stock)
- Stock group queries
- Unit of measure queries
- Godown / warehouse queries
- Stock valuation

Tools available: inventory tools (read-only via MasterTools)
"""

INVENTORY_SYSTEM = """You are FinPilot's Inventory Agent — a specialist in stock management and TallyPrime inventory.

You answer questions about:
- Stock items (products) and their quantities / values
- Low stock alerts and reorder levels
- Stock groups and categories
- Units of measure (Nos, Kg, Ltr, etc.)
- Godowns (warehouses, storage locations)
- Stock valuation and inventory worth

ALWAYS use the provided tools to fetch real stock data before answering.
Present quantities with their units. Present values in Indian currency format (₹12,45,000).
If a stock item or godown doesn't exist, say so clearly — never invent data."""

INVENTORY_TOOL_NAMES = {"get_stock_items", "get_stock_groups", "get_units", "get_godowns"}


class InventoryAgent:
    """Handles inventory-domain questions using MasterTools."""

    system_prompt = INVENTORY_SYSTEM
    tool_names = INVENTORY_TOOL_NAMES
    domain = "inventory"

    def describe(self) -> str:
        return "Inventory specialist: stock items, groups, units, godowns, stock valuation"
