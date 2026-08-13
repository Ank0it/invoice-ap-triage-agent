"""LLM-driven invoice processing agent orchestrator."""

import json
from typing import Any, Dict, List, Optional

from app.agent.llm_client import BaseLLMClient, MockLLMClient
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import is_terminal_state, next_step
from app.agent.tool_schemas import get_openai_tools
from app.agent.validators import (
    ToolCallValidationError,
    validate_final_decision,
    validate_tool_call,
)
from app.models.decision import (
    CheckResult,
    DecisionResult,
    ExceptionCode,
    ExceptionDetail,
    FinalStatus,
    MatchResult,
    ToolTrace,
)
from app.models.invoice import DocumentInspection, ExtractedInvoice
from app.models.tool_result import AgentState, ToolResult
from app.tools.runner import execute_tool, update_state_from_tool_result


SYSTEM_MESSAGE = {
    "role": "system",
    "content": SYSTEM_PROMPT,
}


class LLMInvoiceAgent:
    def __init__(self, llm_client: Optional[BaseLLMClient] = None, max_tool_calls: int = 10):
        self.llm_client = llm_client or MockLLMClient()
        self.max_tool_calls = max_tool_calls

    def process(self, document_path: str, user_instruction: Optional[str] = None) -> DecisionResult:
        state = AgentState(
            document_path=document_path,
            user_instruction=user_instruction,
            max_tool_calls=self.max_tool_calls,
        )
        state.current_step = "inspect_document"

        messages: List[Dict[str, Any]] = [SYSTEM_MESSAGE]
        if user_instruction:
            messages.append({
                "role": "user",
                "content": f"Please process this invoice document. User instruction: {user_instruction}\nDocument path: {document_path}",
            })
        else:
            messages.append({
                "role": "user",
                "content": f"Please process this invoice document. Document path: {document_path}",
            })

        while not is_terminal_state(state.final_status):
            if state.tool_call_count >= self.max_tool_calls:
                state.final_status = FinalStatus.NEEDS_REVIEW
                state.termination_reason = ExceptionCode.AGENT_TOOL_LIMIT_REACHED
                state.exceptions.append(
                    {"code": ExceptionCode.AGENT_TOOL_LIMIT_REACHED, "message": "Maximum tool calls reached."}
                )
                break

            tools = get_openai_tools()
            response = self.llm_client.invoke(messages, tools)

            if response.get("tool_calls"):
                for tool_call in response["tool_calls"]:
                    if state.tool_call_count >= self.max_tool_calls:
                        state.final_status = FinalStatus.NEEDS_REVIEW
                        state.termination_reason = ExceptionCode.AGENT_TOOL_LIMIT_REACHED
                        state.exceptions.append(
                            {"code": ExceptionCode.AGENT_TOOL_LIMIT_REACHED, "message": "Maximum tool calls reached."}
                        )
                        break

                    tool_name = tool_call["name"]
                    arguments = tool_call.get("arguments", {})

                    try:
                        validated_args = validate_tool_call(tool_name, arguments, state)
                    except ToolCallValidationError as exc:
                        error_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", "call-1"),
                            "content": json.dumps({
                                "success": False,
                                "error_code": exc.error_code,
                                "message": exc.message,
                            }),
                        }
                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tool_call],
                        })
                        messages.append(error_msg)
                        state.tool_call_count += 1
                        if exc.error_code == "UNSUPPORTED_TOOL_ARGUMENT":
                            state.final_status = FinalStatus.NEEDS_REVIEW
                            state.termination_reason = ExceptionCode.TOOL_FAILURE
                            state.exceptions.append(
                                {"code": ExceptionCode.TOOL_FAILURE, "message": exc.message}
                            )
                        continue

                    trace = execute_tool(tool_name, state, validated_args)
                    state.tool_trace.append(trace)
                    state.tool_call_count += 1
                    update_state_from_tool_result(state, trace)

                    result_content = {}
                    if trace.success:
                        result_content = {
                            "success": True,
                            "tool": tool_name,
                            "data": self._serialize_tool_data(trace.data),
                        }
                    else:
                        result_content = {
                            "success": False,
                            "error_code": trace.error_code,
                            "message": trace.error_message,
                        }

                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tool_call],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", "call-1"),
                        "content": json.dumps(result_content),
                    })

                if is_terminal_state(state.final_status):
                    break
                continue

            if response.get("content"):
                content = response["content"].strip()
                try:
                    decision = json.loads(content)
                    proposed_status = decision.get("status", "NEEDS_REVIEW")
                    validated_status = validate_final_decision(proposed_status, state)
                    state.final_status = validated_status
                    state.termination_reason = "LLM_FINAL_DECISION"
                    break
                except (json.JSONDecodeError, KeyError):
                    pass

            state.final_status = FinalStatus.NEEDS_REVIEW
            state.termination_reason = ExceptionCode.TOOL_FAILURE
            break

        if state.final_status is None:
            state.final_status, state.termination_reason = self._compute_final_status(state)

        return self._build_result(state)

    def _serialize_tool_data(self, data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if data is None:
            return None
        result = {}
        for key, value in data.items():
            if hasattr(value, "model_dump"):
                result[key] = value.model_dump()
            elif hasattr(value, "dict"):
                result[key] = value.dict()
            else:
                result[key] = value
        return result

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
