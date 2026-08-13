"""Validators for tool arguments and final decisions."""

from typing import Any, Dict, Optional

from app.models.decision import (
    ExceptionCode,
    FinalStatus,
    MatchResult,
    CheckResult,
)


class ToolCallValidationError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(message)


def validate_tool_call(tool_name: str, arguments: Dict[str, Any], state) -> Dict[str, Any]:
    validated = dict(arguments)
    if tool_name == "inspect_document":
        if "document_path" not in validated:
            raise ToolCallValidationError(
                "MISSING_REQUIRED_ARGUMENT",
                "inspect_document requires document_path.",
            )
        return validated

    if tool_name == "extract_invoice":
        if "document_path" not in validated:
            raise ToolCallValidationError(
                "MISSING_REQUIRED_ARGUMENT",
                "extract_invoice requires document_path.",
            )
        return validated

    if tool_name == "lookup_vendor":
        if "name" not in validated or not validated["name"]:
            raise ToolCallValidationError(
                "UNSUPPORTED_TOOL_ARGUMENT",
                "Vendor lookup cannot be performed because no vendor name was reliably extracted.",
            )
        if state.invoice_extraction:
            extracted_name = state.invoice_extraction.vendor_name.value or ""
            if validated["name"].strip().lower() != extracted_name.strip().lower():
                raise ToolCallValidationError(
                    "UNSUPPORTED_TOOL_ARGUMENT",
                    f"Vendor name '{validated['name']}' does not match extracted value '{extracted_name}'.",
                )
        return validated

    if tool_name == "lookup_purchase_order":
        po_number = validated.get("po_number")
        if not po_number:
            raise ToolCallValidationError(
                "UNSUPPORTED_TOOL_ARGUMENT",
                "PO lookup cannot be performed because no PO number was reliably extracted.",
            )
        if state.invoice_extraction:
            extracted_po = state.invoice_extraction.po_number.value or ""
            if po_number.strip().upper() != extracted_po.strip().upper():
                raise ToolCallValidationError(
                    "UNSUPPORTED_TOOL_ARGUMENT",
                    f"PO number '{po_number}' does not match extracted value '{extracted_po}'. Do not invent PO numbers.",
                )
        return validated

    if tool_name == "match_invoice_to_po":
        po_data = validated.get("po_data")
        if not po_data:
            if state.purchase_order_result and state.purchase_order_result.get("status") == "FOUND":
                validated["po_data"] = state.purchase_order_result
            else:
                raise ToolCallValidationError(
                    "UNSUPPORTED_TOOL_ARGUMENT",
                    "match_invoice_to_po requires po_data from a successful lookup_purchase_order result.",
                )
        if state.purchase_order_result and state.purchase_order_result.get("status") != "FOUND":
            raise ToolCallValidationError(
                "UNSUPPORTED_TOOL_ARGUMENT",
                "Cannot match because purchase order lookup did not return FOUND.",
            )
        return validated

    if tool_name == "check_duplicate_invoice":
        vendor_id = validated.get("vendor_id")
        invoice_number = validated.get("invoice_number")
        if not vendor_id or not invoice_number:
            raise ToolCallValidationError(
                "MISSING_REQUIRED_ARGUMENT",
                "Duplicate check requires vendor_id and invoice_number.",
            )
        if state.vendor_result and state.vendor_result.get("status") != "UNIQUE":
            raise ToolCallValidationError(
                "UNSUPPORTED_TOOL_ARGUMENT",
                "Duplicate check requires a uniquely resolved vendor.",
            )
        if state.invoice_extraction:
            extracted_inv = state.invoice_extraction.invoice_number.value or ""
            if invoice_number.strip().upper() != extracted_inv.strip().upper():
                raise ToolCallValidationError(
                    "UNSUPPORTED_TOOL_ARGUMENT",
                    f"Invoice number '{invoice_number}' does not match extracted value '{extracted_inv}'.",
                )
        return validated

    raise ToolCallValidationError(
        "UNKNOWN_TOOL",
        f"Unknown tool: {tool_name}",
    )


def validate_final_decision(proposed_status: str, state) -> str:
    status = proposed_status.strip().upper()
    if status not in {FinalStatus.READY_FOR_REVIEW, FinalStatus.NEEDS_REVIEW, FinalStatus.REJECTED_DOCUMENT}:
        return FinalStatus.NEEDS_REVIEW

    if state.document_inspection:
        if not state.document_inspection.supported:
            return FinalStatus.REJECTED_DOCUMENT
        if not state.document_inspection.readable or "BLURRY" in state.document_inspection.quality_flags:
            return FinalStatus.NEEDS_REVIEW
        if "NO_TEXT_DETECTED" in state.document_inspection.quality_flags:
            return FinalStatus.NEEDS_REVIEW

    if state.vendor_result and state.vendor_result.get("status") == "AMBIGUOUS":
        return FinalStatus.NEEDS_REVIEW

    if state.match_result:
        match_res = state.match_result
        if isinstance(match_res, dict):
            match_res = MatchResult(**match_res)
        if match_res.overall == CheckResult.FAIL:
            return FinalStatus.NEEDS_REVIEW

    if state.duplicate_result and state.duplicate_result.get("duplicate"):
        return FinalStatus.NEEDS_REVIEW

    if state.invoice_extraction and state.invoice_extraction.invoice_number.status in {"MISSING", "UNREADABLE"}:
        return FinalStatus.NEEDS_REVIEW

    return status
