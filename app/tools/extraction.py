"""Invoice extraction tool with OCR and PDF text support."""

import pdfplumber
import re
from pathlib import Path
from typing import List, Optional

from app.models.invoice import (
    CurrencyValue,
    DocumentInspection,
    ExtractedInvoice,
    FieldStatus,
    InvoiceField,
    LineItem,
)


def _normalize_amount(text: str) -> Optional[float]:
    cleaned = re.sub(r"[^0-9.,-]", "", text)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned and "." not in cleaned:
        if cleaned.count(",") == 1 and len(cleaned.split(",")[1]) == 3:
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_text(document_path: str) -> str:
    suffix = Path(document_path).suffix.lower()
    text = ""
    if suffix == ".pdf":
        try:
            with pdfplumber.open(document_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
        except Exception:
            text = ""
    else:
        try:
            import pytesseract
            from PIL import Image

            img = Image.open(document_path)
            text = pytesseract.image_to_string(img)
        except Exception:
            text = ""
    return text


def extract_invoice(
    document_path: str, inspection: Optional[DocumentInspection] = None
) -> ExtractedInvoice:
    if inspection is not None:
        if not inspection.supported:
            return ExtractedInvoice(extraction_notes=["Document format not supported"])
        if "BLURRY" in inspection.quality_flags or "UNREADABLE_DOCUMENT" in inspection.quality_flags:
            return ExtractedInvoice(extraction_notes=["Document quality too low for reliable extraction"])

    text = _extract_text(document_path)
    if not text.strip():
        inv = ExtractedInvoice(extraction_notes=["No text detected in document"])
        return inv

    inv = ExtractedInvoice()

    # Invoice number
    m = re.search(r"Invoice\s*(?:No|Number|#)[:\s]*([A-Z0-9][\w-]+)", text, re.IGNORECASE)
    if m:
        inv.invoice_number = InvoiceField(
            value=m.group(1).strip(),
            confidence=0.9,
            status=FieldStatus.FOUND,
            source_text=m.group(0),
        )

    # Vendor name
    m = re.search(r"(?:From|Sold By|Vendor|Supplier)[:\s]*([A-Za-z][^\n\r]{3,50})", text, re.IGNORECASE)
    if m:
        inv.vendor_name = InvoiceField(
            value=m.group(1).strip(),
            confidence=0.7,
            status=FieldStatus.FOUND,
            source_text=m.group(0),
        )

    # Tax ID / GST
    m = re.search(r"(?:GST|Tax ID|VAT)[:\s]*([A-Z0-9-]{3,20})", text, re.IGNORECASE)
    if m:
        inv.vendor_tax_id = InvoiceField(
            value=m.group(1).strip(),
            confidence=0.8,
            status=FieldStatus.FOUND,
            source_text=m.group(0),
        )

    # Invoice date
    m = re.search(r"Invoice\s*Date[:\s]*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4}|[0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2})", text, re.IGNORECASE)
    if m:
        inv.invoice_date = InvoiceField(
            value=m.group(1).strip(),
            confidence=0.9,
            status=FieldStatus.FOUND,
            source_text=m.group(0),
        )

    # Due date
    m = re.search(r"Due\s*Date[:\s]*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4}|[0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2})", text, re.IGNORECASE)
    if m:
        inv.due_date = InvoiceField(
            value=m.group(1).strip(),
            confidence=0.9,
            status=FieldStatus.FOUND,
            source_text=m.group(0),
        )

    # PO number
    m = re.search(r"P\.?O\.?\s*(?:No|Number|#)?[:\s]*([A-Z0-9][\w-]+)", text, re.IGNORECASE)
    if m:
        inv.po_number = InvoiceField(
            value=m.group(1).strip(),
            confidence=0.85,
            status=FieldStatus.FOUND,
            source_text=m.group(0),
        )

    # Currency
    m = re.search(r"(USD|EUR|GBP|INR|CAD|AUD)\b", text, re.IGNORECASE)
    if m:
        inv.currency = InvoiceField(
            value=m.group(1).upper(),
            confidence=0.95,
            status=FieldStatus.FOUND,
            source_text=m.group(0),
        )

    # Payment terms
    m = re.search(r"(?:Payment\s*Terms|Terms)[:\s]*([^\n\r]{3,50})", text, re.IGNORECASE)
    if m:
        inv.payment_terms = InvoiceField(
            value=m.group(1).strip(),
            confidence=0.7,
            status=FieldStatus.FOUND,
            source_text=m.group(0),
        )

    # Amounts
    def _find_amount(label: str, field: CurrencyValue):
        patterns = [
            rf"\b{re.escape(label)}\b\s*(?:\([^)]*\))?[:\s]*\$?\s*([0-9,]+\.\d{{2}})",
            rf"\b{re.escape(label)}\b[:\s]*\$?\s*([0-9,]+\.\d{{2}})",
        ]
        for pat in patterns:
            m2 = re.search(pat, text, re.IGNORECASE)
            if m2:
                val = _normalize_amount(m2.group(1))
                if val is not None:
                    field.value = val
                    field.confidence = 0.8
                    field.status = FieldStatus.FOUND
                    field.source_text = m2.group(0)
                return

    _find_amount("Subtotal", inv.subtotal)
    _find_amount("Discount", inv.discount)
    _find_amount("Tax", inv.tax)
    _find_amount("Shipping", inv.shipping)
    _find_amount("Total", inv.total)
    _find_amount("Amount Due", inv.amount_due)

    # Line items
    line_pattern = re.compile(
        r"(\d+)\.\s*([A-Za-z][^\d\n\r]{2,40}?)\s+x(\d+)\s+\$?([0-9,]+\.\d{2})\s+\$?([0-9,]+\.\d{2})",
        re.IGNORECASE,
    )
    for lm in line_pattern.finditer(text):
        inv.line_items.append(
            LineItem(
                description=InvoiceField(value=lm.group(2).strip(), status=FieldStatus.FOUND, confidence=0.7),
                quantity=InvoiceField(value=lm.group(3).strip(), status=FieldStatus.FOUND, confidence=0.8),
                unit_price=CurrencyValue(value=_normalize_amount(lm.group(4)), status=FieldStatus.FOUND, confidence=0.8),
                line_total=CurrencyValue(value=_normalize_amount(lm.group(5)), status=FieldStatus.FOUND, confidence=0.8),
            )
        )

    # If total is missing but subtotal + tax + shipping are present, derive it
    if inv.total.status == "MISSING" and inv.subtotal.status == "FOUND":
        derived = inv.subtotal.value or 0.0
        if inv.tax.status == "FOUND":
            derived += inv.tax.value or 0.0
        if inv.shipping.status == "FOUND":
            derived += inv.shipping.value or 0.0
        if derived > 0:
            inv.total.value = round(derived, 2)
            inv.total.confidence = 0.4
            inv.total.status = FieldStatus.UNCERTAIN
            inv.total.source_text = "Derived from subtotal + tax + shipping"
            inv.extraction_notes.append("Total derived from subtotal/tax/shipping")

    return inv
