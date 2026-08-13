"""Models for extracted invoice fields and document inspection."""

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class FieldStatus(str, Enum):
    FOUND = "FOUND"
    MISSING = "MISSING"
    UNCERTAIN = "UNCERTAIN"
    UNREADABLE = "UNREADABLE"
    CONFLICTING = "CONFLICTING"


class CurrencyValue(BaseModel):
    value: Optional[float] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: FieldStatus = FieldStatus.MISSING
    source_text: Optional[str] = None
    candidates: Optional[List[str]] = None


class InvoiceField(BaseModel):
    value: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: FieldStatus = FieldStatus.MISSING
    source_page: Optional[int] = None
    source_text: Optional[str] = None
    candidates: Optional[List[str]] = None


class LineItem(BaseModel):
    description: Optional[InvoiceField] = None
    product_code: Optional[InvoiceField] = None
    quantity: Optional[InvoiceField] = None
    unit_price: Optional[CurrencyValue] = None
    line_total: Optional[CurrencyValue] = None


class DocumentInspection(BaseModel):
    supported: bool = False
    page_count: int = 0
    readable: bool = False
    text_detected: bool = False
    quality_flags: List[str] = Field(default_factory=list)
    file_type: Optional[str] = None
    file_size_bytes: int = 0


class ExtractedInvoice(BaseModel):
    vendor_name: InvoiceField = Field(default_factory=InvoiceField)
    vendor_tax_id: InvoiceField = Field(default_factory=InvoiceField)
    invoice_number: InvoiceField = Field(default_factory=InvoiceField)
    invoice_date: InvoiceField = Field(default_factory=InvoiceField)
    due_date: InvoiceField = Field(default_factory=InvoiceField)
    po_number: InvoiceField = Field(default_factory=InvoiceField)
    currency: InvoiceField = Field(default_factory=InvoiceField)
    payment_terms: InvoiceField = Field(default_factory=InvoiceField)
    subtotal: CurrencyValue = Field(default_factory=CurrencyValue)
    discount: CurrencyValue = Field(default_factory=CurrencyValue)
    tax: CurrencyValue = Field(default_factory=CurrencyValue)
    shipping: CurrencyValue = Field(default_factory=CurrencyValue)
    total: CurrencyValue = Field(default_factory=CurrencyValue)
    amount_due: CurrencyValue = Field(default_factory=CurrencyValue)
    line_items: List[LineItem] = Field(default_factory=list)
    extraction_notes: List[str] = Field(default_factory=list)
