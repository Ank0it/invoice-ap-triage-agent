"""State machine definitions for the invoice agent."""

from app.models.tool_result import AgentState
from app.models.decision import FinalStatus

__all__ = ["AgentState", "FinalStatus"]


def reset_state(document_path: str, user_instruction: str | None = None) -> AgentState:
    return AgentState(document_path=document_path, user_instruction=user_instruction)


def is_terminal_state(status: str | None) -> bool:
    return status in {
        FinalStatus.READY_FOR_REVIEW,
        FinalStatus.NEEDS_REVIEW,
        FinalStatus.REJECTED_DOCUMENT,
    }


def next_step(current_step: str) -> str:
    order = [
        "start",
        "inspect_document",
        "extract_invoice",
        "lookup_vendor",
        "lookup_purchase_order",
        "match_invoice_to_po",
        "check_duplicate_invoice",
        "final_decision",
    ]
    try:
        idx = order.index(current_step)
        if idx < len(order) - 1:
            return order[idx + 1]
    except ValueError:
        pass
    return "final_decision"
