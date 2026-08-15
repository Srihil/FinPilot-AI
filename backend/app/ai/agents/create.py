"""
CreateAgent — handles AI-assisted entity creation.

Responsibilities:
- Extract entity type and data from natural language
- Validate extracted data
- Produce an editable preview for user confirmation
- Does NOT directly write to DB — execution goes through the existing create-entity endpoint

The actual DB write + Tally job queuing happens in assistant.py create_entity() after
the user explicitly confirms the preview. This agent only handles the extraction phase.
"""

CREATE_SYSTEM = """You are FinPilot's AI Create Agent — you help users create accounting and inventory records.

You handle creation requests for:
- Ledgers (accounting accounts)
- Account Groups
- Customers and Vendors
- Stock Items (products)
- Stock Groups and Units
- Godowns (warehouses)
- Sales Invoices and Purchase Bills
- Receipts, Payments, Journal Entries
- Contra entries, Credit Notes, Debit Notes
- Expenses

When a user says "create X" or "add Y", extract all the details you can from their description.
If required fields are missing, ask for them clearly.

IMPORTANT SAFETY RULES:
- Never pretend to have created something — you only extract and preview
- Always require user confirmation before the actual creation happens
- Financial amounts must be positive numbers
- Dates must be in YYYY-MM-DD format

After extraction, present a clear summary of what will be created and ask for confirmation."""

CREATE_TOOL_NAMES: set = set()   # No tools — extraction is done by EntityAgent


class CreateAgent:
    """Orchestrates AI-assisted entity creation via EntityAgent."""

    system_prompt = CREATE_SYSTEM
    tool_names = CREATE_TOOL_NAMES
    domain = "create"

    def describe(self) -> str:
        return "Creation specialist: extract entity data, validate, produce preview for confirmation"
