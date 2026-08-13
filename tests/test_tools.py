"""Tests for deterministic tool behavior."""

import json
import os
import tempfile

import pytest

from app.models.invoice import (
    CurrencyValue,
    DocumentInspection,
    ExtractedInvoice,
    InvoiceField,
    LineItem,
)
from app.models.tool_result import AgentState
from app.tools.document import inspect_document
from app.tools.duplicate import check_duplicate_invoice
from app.tools.extraction import extract_invoice
from app.tools.matching import match_invoice_to_po
from app.tools.purchase_order import lookup_purchase_order
from app.tools.vendor import lookup_vendor


class TestInspectDocument:
    def test_missing_file(self):
        result = inspect_document("/nonexistent/path.pdf")
        assert result.supported is False
        assert "UNSUPPORTED_FORMAT" in result.quality_flags

    def test_blank_document(self, tmp_path):
        from tests.fixtures.generator import generate_blank_invoice
        p = generate_blank_invoice(tmp_path / "blank.pdf")
        result = inspect_document(str(p))
        assert result.supported is True
        assert result.text_detected is False
        assert "NO_TEXT_DETECTED" in result.quality_flags

    def test_quality_flags_are_list(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = inspect_document(str(p))
        assert isinstance(result.quality_flags, list)


class TestExtractInvoice:
    def test_clean_invoice_extraction(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = extract_invoice(str(p))
        assert isinstance(result, ExtractedInvoice)
        assert result.invoice_number.value == "INV-1042"
        assert result.invoice_number.status == "FOUND"
        assert result.po_number.value == "PO-88021"
        assert result.total.value == 1250.00
        assert result.currency.value == "USD"

    def test_blurry_invoice_does_not_invent_values(self, tmp_path):
        from tests.fixtures.generator import generate_blurry_invoice
        p = generate_blurry_invoice(tmp_path / "blurry.pdf")
        result = extract_invoice(str(p))
        if result.invoice_number.status in {"MISSING", "UNREADABLE", "UNCERTAIN"}:
            assert result.invoice_number.value is None
        if result.total.status in {"MISSING", "UNREADABLE", "UNCERTAIN"}:
            assert result.total.value is None

    def test_blank_invoice_no_fields(self, tmp_path):
        from tests.fixtures.generator import generate_blank_invoice
        p = generate_blank_invoice(tmp_path / "blank.pdf")
        result = extract_invoice(str(p))
        assert result.invoice_number.status in {"MISSING", "UNREADABLE"}
        assert result.total.status in {"MISSING", "UNREADABLE"}

    def test_partial_invoice_extraction(self, tmp_path):
        from tests.fixtures.generator import generate_partial_invoice
        p = generate_partial_invoice(tmp_path / "partial.pdf")
        result = extract_invoice(str(p))
        assert result.invoice_number.value == "INV-2049"
        assert result.invoice_number.status == "FOUND"
        assert result.total.status in {"MISSING", "UNREADABLE"}


class TestVendorLookup:
    def test_unique_vendor(self):
        result = lookup_vendor("Acme Supplies")
        assert result["status"] in {"UNIQUE", "AMBIGUOUS", "NONE"}

    def test_ambiguous_vendor(self):
        result = lookup_vendor("Acme Supplies Pvt Ltd")
        assert result["status"] == "AMBIGUOUS"
        assert len(result["matches"]) == 2

    def test_unknown_vendor(self):
        result = lookup_vendor("Zebra Unknown Corp")
        assert result["status"] == "NONE"

    def test_tax_id_filter(self):
        result = lookup_vendor("Acme Supplies", tax_id="GST-123")
        assert result["status"] == "UNIQUE"
        assert result["matches"][0]["vendor_id"] == "V-101"

    def test_wrong_tax_id_returns_none(self):
        result = lookup_vendor("Acme Supplies", tax_id="GST-999")
        assert result["status"] == "NONE"


class TestPurchaseOrderLookup:
    def test_existing_po(self):
        result = lookup_purchase_order("PO-88021")
        assert result["status"] == "FOUND"
        assert result["expected_total"] == 1250.00

    def test_missing_po(self):
        result = lookup_purchase_order("PO-00000")
        assert result["status"] == "NOT_FOUND"

    def test_case_insensitive_po(self):
        result = lookup_purchase_order("po-88021")
        assert result["status"] == "FOUND"

    def test_empty_po(self):
        result = lookup_purchase_order("")
        assert result["status"] == "NOT_FOUND"


class TestMatchInvoiceToPo:
    def _make_extraction(self, po_number="PO-88021", total=1250.00, currency="USD",
                         quantities=(5, 10, 2), unit_prices=(100.00, 25.00, 75.00)):
        inv = ExtractedInvoice()
        inv.po_number = InvoiceField(value=po_number, status="FOUND")
        inv.total = CurrencyValue(value=total, status="FOUND")
        inv.currency = InvoiceField(value=currency, status="FOUND")
        lines = []
        for qty, up in zip(quantities, unit_prices):
            lines.append(LineItem(
                quantity=InvoiceField(value=str(qty), status="FOUND"),
                unit_price=CurrencyValue(value=up, status="FOUND"),
            ))
        inv.line_items = lines
        return inv

    def test_perfect_match(self):
        po = lookup_purchase_order("PO-88021")
        inv = self._make_extraction()
        result = match_invoice_to_po(inv, po)
        assert result.overall.value == "PASS"

    def test_total_mismatch(self):
        po = lookup_purchase_order("PO-88021")
        inv = self._make_extraction(total=1750.00)
        result = match_invoice_to_po(inv, po)
        assert result.overall.value == "FAIL"
        assert result.checks["total_match"].value == "FAIL"

    def test_unit_price_mismatch(self):
        po = lookup_purchase_order("PO-88021")
        inv = self._make_extraction(unit_prices=(55.00, 25.00, 75.00))
        result = match_invoice_to_po(inv, po)
        assert result.overall.value == "FAIL"
        assert result.checks["unit_price_match"].value == "FAIL"

    def test_quantity_mismatch(self):
        po = lookup_purchase_order("PO-88021")
        inv = self._make_extraction(quantities=(6, 10, 2))
        result = match_invoice_to_po(inv, po)
        assert result.overall.value == "FAIL"
        assert result.checks["quantity_match"].value == "FAIL"

    def test_po_not_found(self):
        inv = self._make_extraction(po_number="PO-00000")
        result = match_invoice_to_po(inv, {"status": "NOT_FOUND"})
        assert result.overall.value == "FAIL"

    def test_ambiguous_vendor_no_selection(self):
        po = lookup_purchase_order("PO-88021")
        inv = self._make_extraction()
        result = match_invoice_to_po(inv, po, vendor_matches=[{}, {}])
        assert result.overall.value == "FAIL"
        assert result.checks["vendor_match"].value == "NOT_CHECKED"


class TestDuplicateInvoice:
    def test_duplicate_found(self):
        result = check_duplicate_invoice("V-101", "INV-1042")
        assert result["duplicate"] is True
        assert len(result["matches"]) >= 1

    def test_no_duplicate(self):
        result = check_duplicate_invoice("V-101", "INV-99999")
        assert result["duplicate"] is False

    def test_same_number_different_vendor(self):
        result = check_duplicate_invoice("V-999", "INV-1042")
        assert result["duplicate"] is False

    def test_empty_inputs(self):
        result = check_duplicate_invoice(None, None)
        assert result["duplicate"] is False
