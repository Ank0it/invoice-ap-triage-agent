"""Tests specifically for extraction behavior."""

import os
import tempfile

import pytest

from app.models.invoice import FieldStatus
from app.tools.extraction import extract_invoice


class TestExtractionBehavior:
    def test_clean_invoice_fields(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = extract_invoice(str(p))
        assert result.invoice_number.value == "INV-1042"
        assert result.invoice_number.status == FieldStatus.FOUND
        assert result.po_number.value == "PO-88021"
        assert result.total.value == 1250.00
        assert result.total.status == FieldStatus.FOUND
        assert result.currency.value == "USD"
        assert result.line_items is not None

    def test_no_invention_on_missing_total(self, tmp_path):
        from tests.fixtures.generator import generate_partial_invoice
        p = generate_partial_invoice(tmp_path / "partial.pdf")
        result = extract_invoice(str(p))
        if result.total.status == FieldStatus.MISSING:
            assert result.total.value is None

    def test_no_invention_on_blurry(self, tmp_path):
        from tests.fixtures.generator import generate_blurry_invoice
        p = generate_blurry_invoice(tmp_path / "blurry.pdf")
        result = extract_invoice(str(p))
        if result.invoice_number.status == FieldStatus.MISSING:
            assert result.invoice_number.value is None
        if result.total.status == FieldStatus.MISSING:
            assert result.total.value is None

    def test_currency_extraction(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = extract_invoice(str(p))
        assert result.currency.value == "USD"
        assert result.currency.status == FieldStatus.FOUND

    def test_vendor_name_extraction(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = extract_invoice(str(p))
        assert "Acme" in (result.vendor_name.value or "")
        assert result.vendor_name.status == FieldStatus.FOUND

    def test_tax_id_extraction(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = extract_invoice(str(p))
        assert result.vendor_tax_id.value == "GST-123"
        assert result.vendor_tax_id.status == FieldStatus.FOUND

    def test_date_extraction(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = extract_invoice(str(p))
        assert result.invoice_date.value == "2024-05-15"
        assert result.due_date.value == "2024-06-15"

    def test_payment_terms_extraction(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = extract_invoice(str(p))
        assert "Net 30" in (result.payment_terms.value or "")
