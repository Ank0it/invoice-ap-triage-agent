"""Tool schema definitions for LLM function calling."""

from typing import Any, Dict, List

INSPECT_DOCUMENT_TOOL = {
    "name": "inspect_document",
    "description": "Inspect a document for usability and quality. Use this FIRST before extracting any values. Returns supported format, page count, readability, text detection, and quality flags.",
    "parameters": {
        "type": "object",
        "properties": {
            "document_path": {
                "type": "string",
                "description": "Path to the invoice document (PDF or image file). Always pass the current document_path from state.",
            }
        },
        "required": ["document_path"],
    },
    "returns": {
        "type": "object",
        "properties": {
            "supported": {"type": "boolean"},
            "page_count": {"type": "integer"},
            "readable": {"type": "boolean"},
            "text_detected": {"type": "boolean"},
            "quality_flags": {"type": "array", "items": {"type": "string"}},
            "file_type": {"type": "string"},
            "file_size_bytes": {"type": "integer"},
        },
    },
}

EXTRACT_INVOICE_TOOL = {
    "name": "extract_invoice",
    "description": "Extract structured invoice fields from the document. Must be called AFTER inspect_document confirms the document is readable. Returns fields with confidence and status. Never invent missing values.",
    "parameters": {
        "type": "object",
        "properties": {
            "document_path": {
                "type": "string",
                "description": "Path to the invoice document.",
            },
            "inspection": {
                "type": "object",
                "description": "Optional DocumentInspection result from inspect_document. Pass the inspection result if available.",
            },
        },
        "required": ["document_path"],
    },
    "returns": {
        "type": "object",
        "properties": {
            "vendor_name": {"type": "object"},
            "vendor_tax_id": {"type": "object"},
            "invoice_number": {"type": "object"},
            "invoice_date": {"type": "object"},
            "due_date": {"type": "object"},
            "po_number": {"type": "object"},
            "currency": {"type": "object"},
            "payment_terms": {"type": "object"},
            "subtotal": {"type": "object"},
            "discount": {"type": "object"},
            "tax": {"type": "object"},
            "shipping": {"type": "object"},
            "total": {"type": "object"},
            "amount_due": {"type": "object"},
            "line_items": {"type": "array"},
            "extraction_notes": {"type": "array", "items": {"type": "string"}},
        },
    },
}

LOOKUP_VENDOR_TOOL = {
    "name": "lookup_vendor",
    "description": "Look up a vendor by extracted name and optional tax ID. Use this AFTER extract_invoice returns a vendor_name. If multiple vendors match (AMBIGUOUS), do NOT select one arbitrarily. Return AMBIGUOUS to the user.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Vendor name extracted from the invoice. Must come from extraction result, not from guessing.",
            },
            "tax_id": {
                "type": "string",
                "description": "Optional tax ID extracted from the invoice.",
            },
        },
        "required": ["name"],
    },
    "returns": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["UNIQUE", "NONE", "AMBIGUOUS"]},
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "vendor_id": {"type": "string"},
                        "name": {"type": "string"},
                        "tax_id": {"type": "string"},
                    },
                },
            },
        },
    },
}

LOOKUP_PURCHASE_ORDER_TOOL = {
    "name": "lookup_purchase_order",
    "description": "Look up a purchase order by PO number. ONLY call this if extract_invoice returned a non-null po_number with status FOUND. Do NOT invent a PO number. If no PO was extracted, do not call this tool.",
    "parameters": {
        "type": "object",
        "properties": {
            "po_number": {
                "type": "string",
                "description": "PO number extracted from the invoice. Must be a real extracted value, not invented.",
            }
        },
        "required": ["po_number"],
    },
    "returns": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["FOUND", "NOT_FOUND"]},
            "po_number": {"type": "string"},
            "vendor_id": {"type": "string"},
            "currency": {"type": "string"},
            "status": {"type": "string"},
            "line_items": {"type": "array"},
            "expected_total": {"type": "number"},
        },
    },
}

MATCH_INVOICE_TO_PO_TOOL = {
    "name": "match_invoice_to_po",
    "description": "Deterministically compare extracted invoice fields against PO data. Call this AFTER lookup_purchase_order returns FOUND. The tool performs arithmetic and matching; the LLM must NOT override the result.",
    "parameters": {
        "type": "object",
        "properties": {
            "extraction": {
                "type": "object",
                "description": "ExtractedInvoice object from extract_invoice.",
            },
            "po_data": {
                "type": "object",
                "description": "PO data from lookup_purchase_order. Must be the actual result, not invented.",
            },
            "vendor_matches": {
                "type": "array",
                "description": "Optional vendor matches from lookup_vendor.",
            },
        },
        "required": ["extraction", "po_data"],
    },
    "returns": {
        "type": "object",
        "properties": {
            "overall": {"type": "string", "enum": ["PASS", "FAIL", "NOT_CHECKED"]},
            "checks": {
                "type": "object",
                "properties": {
                    "vendor_match": {"type": "string"},
                    "po_number_match": {"type": "string"},
                    "currency_match": {"type": "string"},
                    "line_items_match": {"type": "string"},
                    "quantity_match": {"type": "string"},
                    "unit_price_match": {"type": "string"},
                    "total_match": {"type": "string"},
                },
            },
            "exceptions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "expected": {"type": "any"},
                        "observed": {"type": "any"},
                        "field": {"type": "string"},
                    },
                },
            },
        },
    },
}

CHECK_DUPLICATE_INVOICE_TOOL = {
    "name": "check_duplicate_invoice",
    "description": "Check if this invoice has already been processed. Call this AFTER lookup_vendor returns UNIQUE and extract_invoice returns an invoice_number. Uses vendor_id + invoice_number as the primary identity.",
    "parameters": {
        "type": "object",
        "properties": {
            "vendor_id": {
                "type": "string",
                "description": "Vendor ID from the UNIQUE vendor lookup result.",
            },
            "invoice_number": {
                "type": "string",
                "description": "Invoice number extracted from the document.",
            },
            "invoice_date": {
                "type": "string",
                "description": "Optional invoice date for additional matching.",
            },
        },
        "required": ["vendor_id", "invoice_number"],
    },
    "returns": {
        "type": "object",
        "properties": {
            "duplicate": {"type": "boolean"},
            "matches": {"type": "array"},
        },
    },
}

ALL_TOOLS = [
    INSPECT_DOCUMENT_TOOL,
    EXTRACT_INVOICE_TOOL,
    LOOKUP_VENDOR_TOOL,
    LOOKUP_PURCHASE_ORDER_TOOL,
    MATCH_INVOICE_TO_PO_TOOL,
    CHECK_DUPLICATE_INVOICE_TOOL,
]

TOOL_FUNCTIONS = {
    "inspect_document": None,  # populated at runtime
    "extract_invoice": None,
    "lookup_vendor": None,
    "lookup_purchase_order": None,
    "match_invoice_to_po": None,
    "check_duplicate_invoice": None,
}


def get_openai_tools() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": tool,
        }
        for tool in ALL_TOOLS
    ]
