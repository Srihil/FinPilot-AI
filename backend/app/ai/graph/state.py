"""
LangGraph state definitions for FinPilot AI workflows.

The state is passed through each graph node and accumulates results.
Secrets and raw credentials are NEVER stored in state.
"""
from typing import TypedDict, Optional, List, Any


class AssistantState(TypedDict):
    """State for the AI Assistant conversation graph."""
    # Identity — set at graph entry, never mutated
    user_id: str
    company_id: str
    role: str
    provider: str

    # Conversation
    messages: List[dict]          # OpenAI-format message history
    query: str                    # current user question

    # Routing
    intent: Optional[str]         # "accounting", "inventory", "tally", "reporting", "general"

    # Tool execution
    tool_calls: List[dict]        # tools the LLM requested
    tool_results: List[dict]      # results returned from tools

    # Output
    final_response: Optional[str]
    is_demo: bool
    error: Optional[str]


class CreateState(TypedDict):
    """State for the AI Create entity workflow graph."""
    # Identity
    user_id: str
    company_id: str
    role: str
    provider: str

    # Input
    raw_text: str                 # user's natural language description

    # Extraction
    entity_type: Optional[str]
    extracted_data: Optional[dict]
    confidence: Optional[float]
    missing_fields: List[str]

    # Validation
    validation_errors: List[str]
    is_valid: bool

    # Confirmation (populated after user reviews preview)
    user_confirmed: bool
    final_data: Optional[dict]

    # Execution
    entity_id: Optional[str]
    tally_queued: bool
    tally_job_id: Optional[str]

    # Output
    final_response: Optional[str]
    error: Optional[str]
    is_demo: bool
