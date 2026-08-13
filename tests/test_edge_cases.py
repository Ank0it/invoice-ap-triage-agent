"""Edge case and critical tests."""

import os
import tempfile
from unittest.mock import patch

import pytest

from app.agent.orchestrator import InvoiceAgent
from app.agent.state import is_terminal_state
from app.models.decision import (
    ExceptionCode,
    FinalStatus,
    CheckResult,
)
from app.models.invoice import CurrencyValue, InvoiceField, LineItem, ExtractedInvoice
from app.models.tool_result import AgentState
from app.tools.document import inspect_document
from app.tools.duplicate import check_duplicate_invoice
from app.tools.extraction import extract_invoice
from app.tools.matching import match_invoice_to_po
from app.tools.purchase_order import lookup_purchase_order
from app.tools.vendor import lookup_vendor


class TestCriticalProveToolLoop:
    def test_extract_po_feeds_lookup(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        extraction = extract_invoice(str(p))
        po_number = extraction.po_number.value
        assert po_number == "PO-88021"
        po_result = lookup_purchase_order(po_number)
        assert po_result["status"] == "FOUND"
        assert po_result["expected_total"] == 1250.00


class TestNoHallucination:
    def test_blurry_invoice_no_invented_values(self, tmp_path):
        from tests.fixtures.generator import generate_blurry_invoice
        p = generate_blurry_invoice(tmp_path / "blurry.pdf")
        inspection = inspect_document(str(p))
        extraction = extract_invoice(str(p), inspection)
        if extraction.invoice_number.status in {"UNREADABLE", "MISSING"}:
            assert extraction.invoice_number.value is None
        if extraction.total.status in {"UNREADABLE", "MISSING"}:
            assert extraction.total.value is None

    def test_blank_document_no_invented_values(self, tmp_path):
        from tests.fixtures.generator import generate_blank_invoice
        p = generate_blank_invoice(tmp_path / "blank.pdf")
        extraction = extract_invoice(str(p))
        assert extraction.invoice_number.status in {"MISSING", "UNREADABLE"}
        assert extraction.invoice_number.value is None
        assert extraction.total.status in {"MISSING", "UNREADABLE"}
        assert extraction.total.value is None


class TestMismatchDetection:
    def test_unit_price_mismatch_detected(self):
        inv = ExtractedInvoice()
        inv.po_number = InvoiceField(value="PO-88021", status="FOUND")
        inv.total = CurrencyValue(value=1250.00, status="FOUND")
        inv.currency = InvoiceField(value="USD", status="FOUND")
        inv.line_items = [
            LineItem(
                quantity=InvoiceField(value="5", status="FOUND"),
                unit_price=CurrencyValue(value=55.00, status="FOUND"),
            )
        ]
        po = lookup_purchase_order("PO-88021")
        result = match_invoice_to_po(inv, po)
        assert result.checks["unit_price_match"].value == "FAIL"
        assert result.overall.value == "FAIL"

    def test_total_mismatch_detected(self, tmp_path):
        from tests.fixtures.generator import generate_wrong_total_invoice
        p = generate_wrong_total_invoice(tmp_path / "wrong.pdf")
        agent = InvoiceAgent()
        result = agent.process(str(p))
        assert result.status == FinalStatus.NEEDS_REVIEW
        assert any(e.code == ExceptionCode.TOTAL_MISMATCH for e in result.exceptions)

    def test_quantity_mismatch_detected(self):
        inv = ExtractedInvoice()
        inv.po_number = InvoiceField(value="PO-88021", status="FOUND")
        inv.total = CurrencyValue(value=1250.00, status="FOUND")
        inv.currency = InvoiceField(value="USD", status="FOUND")
        inv.line_items = [
            LineItem(
                quantity=InvoiceField(value="6", status="FOUND"),
                unit_price=CurrencyValue(value=100.00, status="FOUND"),
            )
        ]
        po = lookup_purchase_order("PO-88021")
        result = match_invoice_to_po(inv, po)
        assert result.checks["quantity_match"].value == "FAIL"
        assert result.overall.value == "FAIL"


class TestAmbiguityHandling:
    def test_ambiguous_vendor_not_selected(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        agent = InvoiceAgent()
        with patch("app.tools.runner.lookup_vendor", return_value={
            "status": "AMBIGUOUS",
            "matches": [
                {"vendor_id": "V-101", "name": "Acme Supplies Pvt Ltd", "tax_id": "GST-123"},
                {"vendor_id": "V-103", "name": "Acme Supplies Pvt Ltd", "tax_id": "GST-789"},
            ],
        }):
            result = agent.process(str(p))
        assert result.status == FinalStatus.NEEDS_REVIEW
        assert ExceptionCode.AMBIGUOUS_VENDOR in result.reason_codes
        assert result.vendor_matches is None or len(result.vendor_matches) != 1


class TestCleanTermination:
    def test_max_tool_calls_triggers_needs_review(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        agent = InvoiceAgent(max_tool_calls=2)
        result = agent.process(str(p))
        assert is_terminal_state(result.status.value)

    def test_tool_failure_does_not_invent(self):
        agent = InvoiceAgent()
        result = agent.process("nonexistent.pdf")
        assert result.status.value in {"NEEDS_REVIEW", "REJECTED_DOCUMENT"}

    def test_vague_request_with_document(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        agent = InvoiceAgent()
        result = agent.process(str(p), user_instruction="Check this.")
        assert is_terminal_state(result.status.value)

    def test_vague_request_without_document(self):
        agent = InvoiceAgent()
        result = agent.process("nonexistent.pdf", user_instruction="Check this.")
        assert result.status.value in {"NEEDS_REVIEW", "REJECTED_DOCUMENT"}


class TestVendorEdgeCases:
    def test_unknown_vendor_needs_review(self, tmp_path):
        from tests.fixtures.generator import generate_partial_invoice
        p = generate_partial_invoice(tmp_path / "partial.pdf")
        agent = InvoiceAgent()
        result = agent.process(str(p))
        assert result.status == FinalStatus.NEEDS_REVIEW


class TestDuplicateEdgeCases:
    def test_same_invoice_number_different_vendor_not_duplicate(self):
        result = check_duplicate_invoice("V-999", "INV-1042")
        assert result["duplicate"] is False
