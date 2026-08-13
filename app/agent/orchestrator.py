"""Invoice processing agent orchestrator (deterministic mode)."""

from typing import Optional

from app.agent.state import is_terminal_state
from app.models.decision import (
    CheckResult,
    ExceptionDetail,
    DecisionResult,
    ExceptionCode,
    FinalStatus,
    MatchResult,
    ToolTrace,
)
from app.models.tool_result import AgentState, ToolResult
from app.tools.runner import execute_tool, update_state_from_tool_result


class InvoiceAgent:
    def __init__(self, max_tool_calls: int = 10):
        self.max_tool_calls = max_tool_calls

    def process(self, document_path: str, user_instruction: Optional[str] = None) -> DecisionResult:
        state = AgentState(
            document_path=document_path,
            user_instruction=user_instruction,
            max_tool_calls=self.max_tool_calls,
        )

        state.current_step = "inspect_document"
        while not is_terminal_state(state.final_status):
            if state.tool_call_count >= self.max_tool_calls:
                state.final_status = FinalStatus.NEEDS_REVIEW
                state.termination_reason = ExceptionCode.AGENT_TOOL_LIMIT_REACHED
                state.exceptions.append(
                    {"code": ExceptionCode.AGENT_TOOL_LIMIT_REACHED, "message": "Maximum tool calls reached."}
                )
                break

            tool_name, input_summary = self._select_tool(state)
            if tool_name is None:
                break

            try:
                trace = execute_tool(tool_name, state)
            except Exception as exc:
                trace = ToolResult(
                    tool=tool_name,
                    step=state.tool_call_count + 1,
                    success=False,
                    input_summary=input_summary,
                    output_summary="",
                    error_code="TOOL_FAILURE",
                    error_message=str(exc),
                    duration_ms=0,
                )
            trace.input_summary = input_summary
            state.tool_trace.append(trace)
            state.tool_call_count += 1

            update_state_from_tool_result(state, trace)

        if state.final_status is None:
            state.final_status, state.termination_reason = self._compute_final_status(state)

        return self._build_result(state)

    def _select_tool(self, state: AgentState):
        step = state.current_step
        if step == "inspect_document":
            return "inspect_document", f"inspect_document({state.document_path})"
        if step == "extract_invoice":
            return "extract_invoice", f"extract_invoice({state.document_path})"
        if step == "lookup_vendor":
            if state.invoice_extraction and state.invoice_extraction.vendor_name.value:
                return "lookup_vendor", f"lookup_vendor({state.invoice_extraction.vendor_name.value})"
            return None, ""
        if step == "lookup_purchase_order":
            if state.invoice_extraction and state.invoice_extraction.po_number.value:
                return "lookup_purchase_order", f"lookup_purchase_order({state.invoice_extraction.po_number.value})"
            return None, ""
        if step == "match_invoice_to_po":
            if state.purchase_order_result and state.purchase_order_result.get("status") == "FOUND":
                return "match_invoice_to_po", "match_invoice_to_po(...)"
            return None, ""
        if step == "check_duplicate_invoice":
            vendor_id = None
            if state.vendor_result and state.vendor_result.get("matches"):
                vendor_id = state.vendor_result["matches"][0].get("vendor_id")
            inv_num = state.invoice_extraction.invoice_number.value if state.invoice_extraction else None
            if vendor_id and inv_num:
                return "check_duplicate_invoice", f"check_duplicate_invoice({vendor_id}, {inv_num})"
            return None, ""
        return None, ""

    def _compute_final_status(self, state: AgentState) -> (str, Optional[str]):
        if state.exceptions:
            code = state.exceptions[-1].get("code")
            if code == ExceptionCode.UNREADABLE_DOCUMENT:
                return FinalStatus.NEEDS_REVIEW, ExceptionCode.UNREADABLE_DOCUMENT
            if code == ExceptionCode.TOOL_FAILURE:
                return FinalStatus.NEEDS_REVIEW, ExceptionCode.TOOL_FAILURE
            if code == ExceptionCode.AGENT_TOOL_LIMIT_REACHED:
                return FinalStatus.NEEDS_REVIEW, ExceptionCode.AGENT_TOOL_LIMIT_REACHED
            if code in {
                ExceptionCode.PO_NOT_FOUND,
                ExceptionCode.AMBIGUOUS_VENDOR,
                ExceptionCode.TOTAL_MISMATCH,
                ExceptionCode.UNIT_PRICE_MISMATCH,
                ExceptionCode.QUANTITY_MISMATCH,
                ExceptionCode.VENDOR_MISMATCH,
                ExceptionCode.DUPLICATE_INVOICE,
                ExceptionCode.CURRENCY_MISMATCH,
                ExceptionCode.MISSING_REQUIRED_FIELD,
            }:
                return FinalStatus.NEEDS_REVIEW, code
        if state.match_result:
            if isinstance(state.match_result, dict):
                match_res = MatchResult(**state.match_result)
            else:
                match_res = state.match_result
            if match_res.overall == CheckResult.FAIL:
                return FinalStatus.NEEDS_REVIEW, ExceptionCode.TOTAL_MISMATCH
        if state.duplicate_result and state.duplicate_result.get("duplicate"):
            return FinalStatus.NEEDS_REVIEW, ExceptionCode.DUPLICATE_INVOICE
        if state.invoice_extraction and state.invoice_extraction.invoice_number.status in {"MISSING", "UNREADABLE"}:
            return FinalStatus.NEEDS_REVIEW, ExceptionCode.MISSING_REQUIRED_FIELD
        return FinalStatus.READY_FOR_REVIEW, None

    def _build_result(self, state: AgentState) -> DecisionResult:
        match_res = None
        if state.match_result:
            if isinstance(state.match_result, dict):
                match_res = MatchResult(**state.match_result)
            else:
                match_res = state.match_result

        trace_list = [
            ToolTrace(
                step=t.step,
                tool=t.tool,
                success=t.success,
                duration_ms=t.duration_ms,
                input_summary=t.input_summary,
                output_summary=t.output_summary,
            )
            for t in state.tool_trace
        ]

        exceptions = [ExceptionDetail(**e) for e in state.exceptions]

        return DecisionResult(
            status=FinalStatus(state.final_status) if state.final_status else FinalStatus.NEEDS_REVIEW,
            reason_codes=[e.code for e in exceptions],
            message=state.termination_reason or "Processing completed.",
            match_result=match_res,
            tool_trace=trace_list,
            exceptions=exceptions,
            extracted_invoice=state.invoice_extraction.model_dump() if state.invoice_extraction else None,
            vendor_matches=state.vendor_result.get("matches") if state.vendor_result else None,
            po_data=state.purchase_order_result,
            duplicate_matches=state.duplicate_result.get("matches") if state.duplicate_result else None,
        )


# Re-export tools for backward compatibility with tests that patch them
from app.tools.document import inspect_document  # noqa: E402
from app.tools.extraction import extract_invoice  # noqa: E402
from app.tools.vendor import lookup_vendor  # noqa: E402
from app.tools.purchase_order import lookup_purchase_order  # noqa: E402
from app.tools.matching import match_invoice_to_po  # noqa: E402
from app.tools.duplicate import check_duplicate_invoice  # noqa: E402
