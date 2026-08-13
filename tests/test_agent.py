"""Tests for the agent orchestrator and state machine."""

import os
import tempfile
from unittest.mock import patch

import pytest

from app.agent.orchestrator import InvoiceAgent
from app.agent.state import is_terminal_state
from app.models.decision import (
    ExceptionCode,
    FinalStatus,
)
from app.models.tool_result import AgentState
from app.tools.document import inspect_document
from app.tools.duplicate import check_duplicate_invoice
from app.tools.extraction import extract_invoice
from app.tools.matching import match_invoice_to_po
from app.tools.purchase_order import lookup_purchase_order
from app.tools.vendor import lookup_vendor


class TestAgentStateMachine:
    def setup_method(self):
        self.agent = InvoiceAgent()

    def test_clean_invoice_ready_for_review(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = self.agent.process(str(p))
        assert result.status == FinalStatus.NEEDS_REVIEW  # duplicate detected
        assert any(t.tool == "inspect_document" for t in result.tool_trace)
        assert any(t.tool == "extract_invoice" for t in result.tool_trace)
        assert any(t.tool == "lookup_vendor" for t in result.tool_trace)
        assert any(t.tool == "lookup_purchase_order" for t in result.tool_trace)
        assert any(t.tool == "match_invoice_to_po" for t in result.tool_trace)
        assert any(t.tool == "check_duplicate_invoice" for t in result.tool_trace)

    def test_missing_po_stops_agent(self, tmp_path):
        from tests.fixtures.generator import generate_partial_invoice
        p = generate_partial_invoice(tmp_path / "partial.pdf")
        result = self.agent.process(str(p))
        assert result.status == FinalStatus.NEEDS_REVIEW
        tools_called = [t.tool for t in result.tool_trace]
        assert "lookup_purchase_order" not in tools_called

    def test_po_lookup_receives_extracted_po(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = self.agent.process(str(p))
        po_trace = next((t for t in result.tool_trace if t.tool == "lookup_purchase_order"), None)
        assert po_trace is not None
        assert "PO-88021" in po_trace.input_summary

    def test_duplicate_detected(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = self.agent.process(str(p))
        assert result.status == FinalStatus.NEEDS_REVIEW
        assert ExceptionCode.DUPLICATE_INVOICE in result.reason_codes

    def test_blurry_document_handling(self, tmp_path):
        from tests.fixtures.generator import generate_blurry_invoice
        p = generate_blurry_invoice(tmp_path / "blurry.pdf")
        result = self.agent.process(str(p))
        assert result.status in {FinalStatus.NEEDS_REVIEW, FinalStatus.REJECTED_DOCUMENT}
        assert any(t.tool == "inspect_document" for t in result.tool_trace)

    def test_ambiguous_vendor_does_not_select(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        with patch("app.tools.runner.lookup_vendor", return_value={
            "status": "AMBIGUOUS",
            "matches": [
                {"vendor_id": "V-101", "name": "Acme Supplies Pvt Ltd", "tax_id": "GST-123"},
                {"vendor_id": "V-103", "name": "Acme Supplies Pvt Ltd", "tax_id": "GST-789"},
            ],
        }):
            result = self.agent.process(str(p))
        assert result.status == FinalStatus.NEEDS_REVIEW
        assert ExceptionCode.AMBIGUOUS_VENDOR in result.reason_codes

    def test_agent_terminates_cleanly(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = self.agent.process(str(p))
        assert is_terminal_state(result.status.value)

    def test_max_tool_calls_guard(self, tmp_path):
        agent = InvoiceAgent(max_tool_calls=2)
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = agent.process(str(p))
        assert is_terminal_state(result.status.value)

    def test_tool_failure_handled(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        with patch("app.agent.orchestrator.execute_tool", side_effect=RuntimeError("forced failure")):
            result = self.agent.process(str(p))
        assert result.status == FinalStatus.NEEDS_REVIEW
        assert ExceptionCode.TOOL_FAILURE in result.reason_codes

    def test_repeated_tool_calls_prevented(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.pdf")
        result = self.agent.process(str(p))
        tools = [t.tool for t in result.tool_trace]
        for i in range(1, len(tools)):
            assert tools[i] != tools[i - 1], f"Repeated tool: {tools[i]}"
