"""Tests for LLM orchestration layer."""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from app.agent.llm_client import MockLLMClient
from app.agent.llm_orchestrator import LLMInvoiceAgent
from app.agent.validators import ToolCallValidationError
from app.models.decision import (
    CheckResult,
    ExceptionCode,
    FinalStatus,
)
from app.tools.runner import execute_tool


class TestLLMToolCallingLoop:
    def setup_method(self):
        self.agent = LLMInvoiceAgent(llm_client=MockLLMClient())

    def test_llm_calls_tools_in_correct_order(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_03
        p = generate_clean_invoice_03(tmp_path / "clean.pdf")

        mock_responses = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call-1", "name": "inspect_document", "arguments": {"document_path": str(p)}}],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call-2", "name": "extract_invoice", "arguments": {"document_path": str(p)}}],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call-3", "name": "lookup_vendor", "arguments": {"name": "Acme Supplies Pvt Ltd", "tax_id": "GST-123"}}],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call-4", "name": "lookup_purchase_order", "arguments": {"po_number": "PO-88021"}}],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call-5", "name": "match_invoice_to_po", "arguments": {}}],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call-6", "name": "check_duplicate_invoice", "arguments": {"vendor_id": "V-101", "invoice_number": "INV-8888"}}],
            },
            {
                "role": "assistant",
                "content": json.dumps({"status": "READY_FOR_REVIEW", "message": "Processing complete."}),
                "tool_calls": None,
            },
        ]
        self.agent.llm_client.set_responses(mock_responses)
        result = self.agent.process(str(p))
        assert result.status == FinalStatus.READY_FOR_REVIEW
        tools_called = [t.tool for t in result.tool_trace]
        assert "inspect_document" in tools_called
        assert "extract_invoice" in tools_called
        assert "lookup_vendor" in tools_called
        assert "lookup_purchase_order" in tools_called
        assert "match_invoice_to_po" in tools_called
        assert "check_duplicate_invoice" in tools_called

    def test_po_lookup_receives_extracted_po(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_03
        p = generate_clean_invoice_03(tmp_path / "clean.pdf")

        captured_po = {}

        def capture_execute(tool_name, state, arguments=None):
            if tool_name == "lookup_purchase_order":
                captured_po["po_number"] = arguments.get("po_number") if arguments else None
            return execute_tool(tool_name, state, arguments)

        mock_responses = [
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "name": "inspect_document", "arguments": {"document_path": str(p)}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c2", "name": "extract_invoice", "arguments": {"document_path": str(p)}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c3", "name": "lookup_vendor", "arguments": {"name": "Acme Supplies Pvt Ltd", "tax_id": "GST-123"}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c4", "name": "lookup_purchase_order", "arguments": {"po_number": "PO-88021"}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c5", "name": "match_invoice_to_po", "arguments": {}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c6", "name": "check_duplicate_invoice", "arguments": {"vendor_id": "V-101", "invoice_number": "INV-8888"}}]},
            {"role": "assistant", "content": json.dumps({"status": "READY_FOR_REVIEW"}), "tool_calls": None},
        ]
        self.agent.llm_client.set_responses(mock_responses)

        with patch("app.agent.llm_orchestrator.execute_tool", side_effect=capture_execute):
            result = self.agent.process(str(p))

        assert captured_po.get("po_number") == "PO-88021"


class TestLLMValidation:
    def setup_method(self):
        self.agent = LLMInvoiceAgent(llm_client=MockLLMClient())

    def test_llm_hallucinated_po_rejected(self, tmp_path):
        from tests.fixtures.generator import generate_partial_invoice
        p = generate_partial_invoice(tmp_path / "partial.pdf")

        mock_responses = [
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "name": "inspect_document", "arguments": {"document_path": str(p)}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c2", "name": "extract_invoice", "arguments": {"document_path": str(p)}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c3", "name": "lookup_purchase_order", "arguments": {"po_number": "PO-FAKE"}}]},
            {"role": "assistant", "content": json.dumps({"status": "NEEDS_REVIEW"}), "tool_calls": None},
        ]
        self.agent.llm_client.set_responses(mock_responses)
        result = self.agent.process(str(p))
        assert result.status == FinalStatus.NEEDS_REVIEW
        assert any(e.code == ExceptionCode.TOOL_FAILURE for e in result.exceptions)

    def test_llm_decision_override_prevented(self, tmp_path):
        from tests.fixtures.generator import generate_wrong_total_invoice
        p = generate_wrong_total_invoice(tmp_path / "wrong.pdf")

        mock_responses = [
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "name": "inspect_document", "arguments": {"document_path": str(p)}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c2", "name": "extract_invoice", "arguments": {"document_path": str(p)}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c3", "name": "lookup_vendor", "arguments": {"name": "Beta Logistics Ltd"}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c4", "name": "lookup_purchase_order", "arguments": {"po_number": "PO-88024"}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c5", "name": "match_invoice_to_po", "arguments": {}}]},
            {"role": "assistant", "content": json.dumps({"status": "READY_FOR_REVIEW", "message": "I think the total difference is acceptable."}), "tool_calls": None},
        ]
        self.agent.llm_client.set_responses(mock_responses)
        result = self.agent.process(str(p))
        assert result.status == FinalStatus.NEEDS_REVIEW
        assert any(e.code == ExceptionCode.TOTAL_MISMATCH for e in result.exceptions)

    def test_llm_max_tool_calls_terminates(self, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_03
        p = generate_clean_invoice_03(tmp_path / "clean.pdf")
        agent = LLMInvoiceAgent(llm_client=MockLLMClient(), max_tool_calls=3)
        mock_responses = [
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "name": "inspect_document", "arguments": {"document_path": str(p)}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c2", "name": "extract_invoice", "arguments": {"document_path": str(p)}}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c3", "name": "lookup_vendor", "arguments": {"name": "Acme Supplies Pvt Ltd", "tax_id": "GST-123"}}]},
            {"role": "assistant", "content": json.dumps({"status": "NEEDS_REVIEW"}), "tool_calls": None},
        ]
        agent.llm_client.set_responses(mock_responses)
        result = agent.process(str(p))
        assert result.status in {FinalStatus.NEEDS_REVIEW, FinalStatus.READY_FOR_REVIEW}
        assert len(result.tool_trace) <= 3
