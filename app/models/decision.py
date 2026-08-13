"""Models for final decisions and matching results."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FinalStatus(str, Enum):
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED_DOCUMENT = "REJECTED_DOCUMENT"


class CheckResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_CHECKED = "NOT_CHECKED"


class ExceptionCode(str, Enum):
    VENDOR_MISMATCH = "VENDOR_MISMATCH"
    PO_NOT_FOUND = "PO_NOT_FOUND"
    PO_VENDOR_MISMATCH = "PO_VENDOR_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    UNIT_PRICE_MISMATCH = "UNIT_PRICE_MISMATCH"
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    AMBIGUOUS_VENDOR = "AMBIGUOUS_VENDOR"
    UNREADABLE_DOCUMENT = "UNREADABLE_DOCUMENT"
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
    TOOL_FAILURE = "TOOL_FAILURE"
    AGENT_TOOL_LIMIT_REACHED = "AGENT_TOOL_LIMIT_REACHED"


class ExceptionDetail(BaseModel):
    code: ExceptionCode
    message: str
    expected: Optional[Any] = None
    observed: Optional[Any] = None
    field: Optional[str] = None


class MatchResult(BaseModel):
    overall: CheckResult = CheckResult.NOT_CHECKED
    checks: Dict[str, CheckResult] = Field(default_factory=dict)
    exceptions: List[ExceptionDetail] = Field(default_factory=list)


class ToolTrace(BaseModel):
    step: int
    tool: str
    success: bool
    duration_ms: int
    input_summary: str = ""
    output_summary: str = ""


class DecisionResult(BaseModel):
    status: FinalStatus
    reason_codes: List[ExceptionCode] = Field(default_factory=list)
    message: str = ""
    match_result: Optional[MatchResult] = None
    tool_trace: List[ToolTrace] = Field(default_factory=list)
    exceptions: List[ExceptionDetail] = Field(default_factory=list)
    extracted_invoice: Optional[Any] = None
    vendor_matches: Optional[List[Dict[str, Any]]] = None
    po_data: Optional[Dict[str, Any]] = None
    duplicate_matches: Optional[List[Dict[str, Any]]] = None
