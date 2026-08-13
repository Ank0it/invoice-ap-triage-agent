"""Shared tool execution logic for deterministic and LLM orchestrators."""

import time
from typing import Any, Dict, Optional

from app.agent.state import next_step
from app.models.decision import (
    ExceptionCode,
    FinalStatus,
    MatchResult,
)
from app.models.invoice import DocumentInspection, ExtractedInvoice
from app.models.tool_result import ToolResult
from app.tools.document import inspect_document
from app.tools.duplicate import check_duplicate_invoice
from app.tools.extraction import extract_invoice
from app.tools.matching import match_invoice_to_po
from app.tools.purchase_order import lookup_purchase_order
from app.tools.vendor import lookup_vendor


def execute_tool(tool_name: str, state, arguments: Optional[Dict[str, Any]] = None) -> ToolResult:
    arguments = arguments or {}
    start = time.time()
    try:
        if tool_name == "inspect_document":
            document_path = arguments.get("document_path", state.document_path)
            inspection = inspect_document(document_path)
            duration = int((time.time() - start) * 1000)
            return ToolResult(
                tool="inspect_document",
                step=state.tool_call_count + 1,
                success=True,
                input_summary=f"inspect_document({document_path})",
                output_summary=f"supported={inspection.supported}, readable={inspection.readable}, flags={inspection.quality_flags}",
                duration_ms=duration,
                data={"inspection": inspection},
            )

        if tool_name == "extract_invoice":
            document_path = arguments.get("document_path", state.document_path)
            inspection = arguments.get("inspection", state.document_inspection)
            invoice = extract_invoice(document_path, inspection)
            duration = int((time.time() - start) * 1000)
            summary = ""
            if invoice.invoice_number.value:
                summary += f"INV={invoice.invoice_number.value} "
            if invoice.po_number.value:
                summary += f"PO={invoice.po_number.value} "
            if invoice.total.value:
                summary += f"Total={invoice.total.value}"
            return ToolResult(
                tool="extract_invoice",
                step=state.tool_call_count + 1,
                success=True,
                input_summary=f"extract_invoice({document_path})",
                output_summary=summary.strip() or "Fields extracted with uncertainty",
                duration_ms=duration,
                data={"invoice": invoice},
            )

        if tool_name == "lookup_vendor":
            name = arguments.get("name")
            tax_id = arguments.get("tax_id")
            if name is None and state.invoice_extraction:
                name = state.invoice_extraction.vendor_name.value or ""
            if tax_id is None and state.invoice_extraction and state.invoice_extraction.vendor_tax_id:
                tax_id = state.invoice_extraction.vendor_tax_id.value
            result = lookup_vendor(name, tax_id)
            duration = int((time.time() - start) * 1000)
            summary = f"status={result['status']}, matches={len(result.get('matches', []))}"
            return ToolResult(
                tool="lookup_vendor",
                step=state.tool_call_count + 1,
                success=True,
                input_summary=f"lookup_vendor({name})",
                output_summary=summary,
                duration_ms=duration,
                data={"vendor_result": result},
            )

        if tool_name == "lookup_purchase_order":
            po_number = arguments.get("po_number")
            if po_number is None and state.invoice_extraction:
                po_number = state.invoice_extraction.po_number.value or ""
            result = lookup_purchase_order(po_number)
            duration = int((time.time() - start) * 1000)
            summary = f"status={result.get('status')}"
            return ToolResult(
                tool="lookup_purchase_order",
                step=state.tool_call_count + 1,
                success=True,
                input_summary=f"lookup_purchase_order({po_number})",
                output_summary=summary,
                duration_ms=duration,
                data={"po_result": result},
            )

        if tool_name == "match_invoice_to_po":
            extraction = arguments.get("extraction", state.invoice_extraction)
            po_data = arguments.get("po_data", state.purchase_order_result)
            vendor_matches = arguments.get("vendor_matches")
            if vendor_matches is None and state.vendor_result:
                vendor_matches = state.vendor_result.get("matches")
            result = match_invoice_to_po(extraction, po_data, vendor_matches)
            duration = int((time.time() - start) * 1000)
            summary = f"overall={result.overall}, exceptions={len(result.exceptions)}"
            return ToolResult(
                tool="match_invoice_to_po",
                step=state.tool_call_count + 1,
                success=True,
                input_summary="match_invoice_to_po(...)",
                output_summary=summary,
                duration_ms=duration,
                data={"match_result": result},
            )

        if tool_name == "check_duplicate_invoice":
            vendor_id = arguments.get("vendor_id")
            invoice_number = arguments.get("invoice_number")
            invoice_date = arguments.get("invoice_date")
            if vendor_id is None and state.vendor_result and state.vendor_result.get("matches"):
                vendor_id = state.vendor_result["matches"][0].get("vendor_id")
            if invoice_number is None and state.invoice_extraction:
                invoice_number = state.invoice_extraction.invoice_number.value
            result = check_duplicate_invoice(vendor_id, invoice_number, invoice_date)
            duration = int((time.time() - start) * 1000)
            summary = f"duplicate={result.get('duplicate')}, matches={len(result.get('matches', []))}"
            return ToolResult(
                tool="check_duplicate_invoice",
                step=state.tool_call_count + 1,
                success=True,
                input_summary=f"check_duplicate_invoice({vendor_id}, {invoice_number})",
                output_summary=summary,
                duration_ms=duration,
                data={"duplicate_result": result},
            )

        duration = int((time.time() - start) * 1000)
        return ToolResult(
            tool="unknown",
            step=state.tool_call_count + 1,
            success=False,
            input_summary=str(arguments),
            output_summary="Unknown tool",
            error_code="UNKNOWN_TOOL",
            error_message="Tool not recognized.",
            duration_ms=duration,
        )
    except Exception as exc:
        duration = int((time.time() - start) * 1000)
        return ToolResult(
            tool=tool_name,
            step=state.tool_call_count + 1,
            success=False,
            input_summary=str(arguments),
            output_summary="",
            error_code="TOOL_FAILURE",
            error_message=str(exc),
            duration_ms=duration,
        )


def update_state_from_tool_result(state, trace: ToolResult):
    if not trace.success:
        state.exceptions.append(
            {
                "code": ExceptionCode.TOOL_FAILURE,
                "message": trace.error_message or "Tool execution failed.",
            }
        )
        state.final_status = FinalStatus.NEEDS_REVIEW
        state.termination_reason = ExceptionCode.TOOL_FAILURE
        return

    tool_name = trace.tool

    if tool_name == "inspect_document":
        state.document_inspection = trace.data.get("inspection")
        if not state.document_inspection or not state.document_inspection.supported:
            state.final_status = FinalStatus.REJECTED_DOCUMENT
            state.termination_reason = ExceptionCode.UNREADABLE_DOCUMENT
            state.exceptions.append(
                {"code": ExceptionCode.UNREADABLE_DOCUMENT, "message": "Unsupported document format."}
            )
            return
        if not state.document_inspection.readable or "BLURRY" in state.document_inspection.quality_flags or "UNREADABLE_DOCUMENT" in state.document_inspection.quality_flags:
            state.final_status = FinalStatus.NEEDS_REVIEW
            state.termination_reason = ExceptionCode.UNREADABLE_DOCUMENT
            state.exceptions.append(
                {"code": ExceptionCode.UNREADABLE_DOCUMENT, "message": "Document quality is insufficient for reliable extraction."}
            )
            return
        if "NO_TEXT_DETECTED" in state.document_inspection.quality_flags:
            state.final_status = FinalStatus.NEEDS_REVIEW
            state.termination_reason = ExceptionCode.UNREADABLE_DOCUMENT
            state.exceptions.append(
                {"code": ExceptionCode.UNREADABLE_DOCUMENT, "message": "No text detected; document may be scanned without OCR."}
            )
            return
        state.current_step = next_step(state.current_step)

    elif tool_name == "extract_invoice":
        state.invoice_extraction = trace.data.get("invoice", ExtractedInvoice())
        state.current_step = next_step(state.current_step)

    elif tool_name == "lookup_vendor":
        state.vendor_result = trace.data.get("vendor_result")
        if state.vendor_result and state.vendor_result.get("status") == "AMBIGUOUS":
            state.exceptions.append(
                {
                    "code": ExceptionCode.AMBIGUOUS_VENDOR,
                    "message": "Multiple vendors matched the extracted name.",
                }
            )
            state.final_status = FinalStatus.NEEDS_REVIEW
            state.termination_reason = ExceptionCode.AMBIGUOUS_VENDOR
            return
        state.current_step = next_step(state.current_step)

    elif tool_name == "lookup_purchase_order":
        state.purchase_order_result = trace.data.get("po_result")
        if not state.purchase_order_result or state.purchase_order_result.get("status") != "FOUND":
            state.exceptions.append(
                {
                    "code": ExceptionCode.PO_NOT_FOUND,
                    "message": "Purchase order not found.",
                }
            )
            state.final_status = FinalStatus.NEEDS_REVIEW
            state.termination_reason = ExceptionCode.PO_NOT_FOUND
            return
        state.current_step = next_step(state.current_step)

    elif tool_name == "match_invoice_to_po":
        state.match_result = trace.data.get("match_result")
        if state.match_result:
            excs = []
            if isinstance(state.match_result, dict):
                excs = state.match_result.get("exceptions", [])
            elif hasattr(state.match_result, "exceptions"):
                excs = state.match_result.exceptions
            for exc in excs:
                if isinstance(exc, dict):
                    state.exceptions.append(exc)
                elif hasattr(exc, "model_dump"):
                    state.exceptions.append(exc.model_dump())
        state.current_step = next_step(state.current_step)

    elif tool_name == "check_duplicate_invoice":
        state.duplicate_result = trace.data.get("duplicate_result")
        if state.duplicate_result and state.duplicate_result.get("duplicate"):
            state.exceptions.append(
                {"code": ExceptionCode.DUPLICATE_INVOICE, "message": "Duplicate invoice detected."}
            )
        state.current_step = next_step(state.current_step)
