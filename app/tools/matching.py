"""Deterministic invoice-to-PO matching tool."""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.models.decision import (
    CheckResult,
    ExceptionCode,
    ExceptionDetail,
    MatchResult,
)


def _to_dec(val: Any) -> Optional[Decimal]:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


def match_invoice_to_po(
    extraction: Any, po_data: Optional[dict], vendor_matches: Optional[list] = None
) -> MatchResult:
    checks: Dict[str, CheckResult] = {}
    exceptions: List[ExceptionDetail] = []

    vendor_id = None
    if vendor_matches and len(vendor_matches) == 1:
        vendor_id = vendor_matches[0].get("vendor_id")
    elif vendor_matches and len(vendor_matches) > 1:
        checks["vendor_match"] = CheckResult.NOT_CHECKED
        exceptions.append(
            ExceptionDetail(
                code=ExceptionCode.AMBIGUOUS_VENDOR,
                message="Multiple vendors match the extracted name.",
            )
        )
        return MatchResult(overall=CheckResult.FAIL, checks=checks, exceptions=exceptions)

    if po_data is None or po_data.get("status") != "FOUND":
        checks["po_number_match"] = CheckResult.NOT_CHECKED
        exceptions.append(
            ExceptionDetail(
                code=ExceptionCode.PO_NOT_FOUND,
                message="Purchase order not found.",
            )
        )
        return MatchResult(overall=CheckResult.FAIL, checks=checks, exceptions=exceptions)

    # Vendor match
    po_vendor_id = po_data.get("vendor_id")
    if vendor_id and po_vendor_id:
        if vendor_id == po_vendor_id:
            checks["vendor_match"] = CheckResult.PASS
        else:
            checks["vendor_match"] = CheckResult.FAIL
            exceptions.append(
                ExceptionDetail(
                    code=ExceptionCode.VENDOR_MISMATCH,
                    message="Invoice vendor does not match PO vendor.",
                    expected=po_vendor_id,
                    observed=vendor_id,
                )
            )
    else:
        checks["vendor_match"] = CheckResult.NOT_CHECKED

    # PO number match
    po_number = po_data.get("po_number", "")
    inv_po = extraction.po_number.value if extraction and extraction.po_number else None
    if inv_po and po_number:
        if inv_po.strip().upper() == po_number.strip().upper():
            checks["po_number_match"] = CheckResult.PASS
        else:
            checks["po_number_match"] = CheckResult.FAIL
            exceptions.append(
                ExceptionDetail(
                    code=ExceptionCode.PO_NOT_FOUND,
                    message="PO number mismatch.",
                    expected=po_number,
                    observed=inv_po,
                )
            )
    else:
        checks["po_number_match"] = CheckResult.NOT_CHECKED

    # Currency match
    po_currency = po_data.get("currency", "USD").upper()
    inv_currency = (extraction.currency.value or "").upper() if extraction else ""
    if inv_currency and po_currency:
        if inv_currency == po_currency:
            checks["currency_match"] = CheckResult.PASS
        else:
            checks["currency_match"] = CheckResult.FAIL
            exceptions.append(
                ExceptionDetail(
                    code=ExceptionCode.CURRENCY_MISMATCH,
                    message="Currency mismatch.",
                    expected=po_currency,
                    observed=inv_currency,
                )
            )
    else:
        checks["currency_match"] = CheckResult.NOT_CHECKED

    # Line items match
    po_lines = po_data.get("line_items", [])
    inv_lines = extraction.line_items if extraction else []
    line_items_match = True
    quantity_match = True
    unit_price_match = True

    for idx, po_line in enumerate(po_lines):
        if idx >= len(inv_lines):
            line_items_match = False
            quantity_match = False
            unit_price_match = False
            continue

        inv_line = inv_lines[idx]
        po_qty = _to_dec(po_line.get("quantity"))
        inv_qty = _to_dec(inv_line.quantity.value) if inv_line and inv_line.quantity else None
        po_up = _to_dec(po_line.get("unit_price"))
        inv_up = _to_dec(inv_line.unit_price.value) if inv_line and inv_line.unit_price else None

        if po_qty is not None and inv_qty is not None:
            if po_qty != inv_qty:
                quantity_match = False
                exceptions.append(
                    ExceptionDetail(
                        code=ExceptionCode.QUANTITY_MISMATCH,
                        message=f"Quantity mismatch on line {idx + 1}.",
                        expected=float(po_qty),
                        observed=float(inv_qty),
                        field="quantity",
                    )
                )
        elif po_qty is not None and inv_qty is None:
            quantity_match = False
        if po_up is not None and inv_up is not None:
            if po_up != inv_up:
                unit_price_match = False
                exceptions.append(
                    ExceptionDetail(
                        code=ExceptionCode.UNIT_PRICE_MISMATCH,
                        message=f"Unit price mismatch on line {idx + 1}.",
                        expected=float(po_up),
                        observed=float(inv_up),
                        field="unit_price",
                    )
                )
        elif po_up is not None and inv_up is None:
            unit_price_match = False

    # If there are extra invoice lines not in PO, mark as mismatch
    if len(inv_lines) > len(po_lines):
        line_items_match = False

    checks["line_items_match"] = CheckResult.PASS if line_items_match else CheckResult.FAIL
    checks["quantity_match"] = CheckResult.PASS if quantity_match else CheckResult.FAIL
    checks["unit_price_match"] = CheckResult.PASS if unit_price_match else CheckResult.FAIL

    # Total match
    po_total = _to_dec(po_data.get("expected_total"))
    inv_total = _to_dec(extraction.total.value) if extraction and extraction.total else None
    if po_total is not None and inv_total is not None:
        if po_total == inv_total:
            checks["total_match"] = CheckResult.PASS
        else:
            checks["total_match"] = CheckResult.FAIL
            exceptions.append(
                ExceptionDetail(
                    code=ExceptionCode.TOTAL_MISMATCH,
                    message="Total amount does not match PO.",
                    expected=float(po_total),
                    observed=float(inv_total),
                    field="total",
                )
            )
    else:
        checks["total_match"] = CheckResult.NOT_CHECKED

    overall = (
        CheckResult.PASS
        if all(c == CheckResult.PASS or c == CheckResult.NOT_CHECKED for c in checks.values())
        else CheckResult.FAIL
    )

    return MatchResult(overall=overall, checks=checks, exceptions=exceptions)
