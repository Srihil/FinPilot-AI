"""
LangGraph-based AI Create workflow.

Architecture:
  Natural language
    → extract_node     (EntityAgent extracts structured data)
    → validate_node    (check required fields, types)
    → [user reviews preview externally]
    → execute_node     (called after user confirms — via separate API)

The graph state represents the CREATE workflow for one entity.
Actual DB writes and Tally job queuing happen in execute_node via existing services.
AI cannot bypass RBAC, validation, or Tally job queue.
"""
import logging
try:
    from langgraph.graph import StateGraph, END
except ImportError:
    StateGraph = None
    END = None

from app.ai.graph.state import CreateState
from app.agents.entity_agent import EntityAgent

logger = logging.getLogger(__name__)

REQUIRED_FIELDS: dict[str, list[str]] = {
    "ledger": ["name"],
    "group": ["name", "parent"],
    "customer": ["name"],
    "vendor": ["name"],
    "stock_item": ["name"],
    "stock_group": ["name"],
    "unit": ["name"],
    "godown": ["name"],
    "sales_invoice": ["customer_name", "amount"],
    "purchase_bill": ["vendor_name", "amount"],
    "receipt": ["party_ledger", "amount"],
    "payment": ["party_ledger", "amount"],
    "journal": ["dr_ledger", "cr_ledger", "amount"],
    "credit_note": ["party_ledger", "amount"],
    "debit_note": ["party_ledger", "amount"],
    "contra": ["from_account", "to_account", "amount"],
    "expense": ["title", "amount"],
}


def extract_node(state: CreateState) -> dict:
    """Use EntityAgent to extract structured data from natural language."""
    agent = EntityAgent()
    try:
        result = agent.extract(state["raw_text"])
        return {
            "entity_type": result.get("entity_type"),
            "extracted_data": result.get("data", {}),
            "confidence": result.get("confidence", 0.0),
            "missing_fields": result.get("missing_fields", []),
            "is_demo": False,
        }
    except Exception as e:
        logger.error("Entity extraction failed: %s", e)
        return {
            "entity_type": None,
            "extracted_data": {},
            "confidence": 0.0,
            "missing_fields": [],
            "error": str(e),
            "is_demo": False,
        }


def validate_node(state: CreateState) -> dict:
    """Validate extracted data against required fields for the entity type."""
    entity_type = state.get("entity_type")
    data = state.get("extracted_data") or {}
    errors = []

    if not entity_type:
        errors.append("Could not determine entity type from your description.")
        return {"validation_errors": errors, "is_valid": False}

    required = REQUIRED_FIELDS.get(entity_type, [])
    for field in required:
        val = data.get(field)
        if not val and val != 0:
            errors.append(f"Required field missing: {field}")

    # Amount must be positive for financial entities
    if "amount" in data:
        try:
            amt = float(data["amount"])
            if amt <= 0:
                errors.append("Amount must be greater than zero.")
        except (TypeError, ValueError):
            errors.append("Amount must be a valid number.")

    return {
        "validation_errors": errors,
        "is_valid": len(errors) == 0,
    }


def build_create_graph():
    """Build and compile the entity creation LangGraph (extract + validate phase only)."""
    if StateGraph is None:
        raise ImportError("langgraph is not installed")
    graph = StateGraph(CreateState)

    graph.add_node("extract", extract_node)
    graph.add_node("validate", validate_node)

    graph.set_entry_point("extract")
    graph.add_edge("extract", "validate")
    graph.add_edge("validate", END)

    return graph.compile()


def run_create_extraction(
    raw_text: str,
    user_id: str,
    company_id: str,
    role: str,
    provider: str,
) -> dict:
    """Run the extraction phase of AI Create. Returns structured preview for user confirmation."""
    graph = build_create_graph()

    initial_state: CreateState = {
        "user_id": user_id,
        "company_id": company_id,
        "role": role,
        "provider": provider,
        "raw_text": raw_text,
        "entity_type": None,
        "extracted_data": None,
        "confidence": None,
        "missing_fields": [],
        "validation_errors": [],
        "is_valid": False,
        "user_confirmed": False,
        "final_data": None,
        "entity_id": None,
        "tally_queued": False,
        "tally_job_id": None,
        "final_response": None,
        "error": None,
        "is_demo": False,
    }

    result = graph.invoke(initial_state)
    return {
        "entity_type": result.get("entity_type"),
        "data": result.get("extracted_data", {}),
        "confidence": result.get("confidence", 0.0),
        "missing_fields": result.get("missing_fields", []),
        "validation_errors": result.get("validation_errors", []),
        "is_valid": result.get("is_valid", False),
        "is_demo": result.get("is_demo", False),
        "error": result.get("error"),
    }
