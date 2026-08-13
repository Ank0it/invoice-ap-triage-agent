"""Models for tool results and agent state."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.invoice import ExtractedInvoice


class ToolResultStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    BLOCKED = "BLOCKED"


class ToolResult(BaseModel):
    tool: str
    step: int
    success: bool
    input_summary: str = ""
    output_summary: str = ""
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Optional[Dict[str, Any]] = None


class AgentState(BaseModel):
    document_path: Optional[str] = None
    user_instruction: Optional[str] = None
    document_inspection: Optional[Any] = None
    invoice_extraction: ExtractedInvoice = Field(default_factory=ExtractedInvoice)
    vendor_result: Optional[Dict[str, Any]] = None
    purchase_order_result: Optional[Dict[str, Any]] = None
    match_result: Optional[Dict[str, Any]] = None
    duplicate_result: Optional[Dict[str, Any]] = None
    exceptions: List[Dict[str, Any]] = Field(default_factory=list)
    tool_trace: List[ToolResult] = Field(default_factory=list)
    current_step: str = "start"
    final_status: Optional[str] = None
    tool_call_count: int = 0
    max_tool_calls: int = 10
    termination_reason: Optional[str] = None
