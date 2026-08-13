# Invoice Intake & Accounts Payable Exception Triage Agent

An invoice-processing agent that uses deterministic tools to extract and verify invoice information. The agent never invents business facts; all values come from document extraction or deterministic lookup tools.

## 1. What the project does

This system accepts an invoice document (PDF or image), inspects it for usability, extracts structured invoice fields, looks up the vendor and purchase order in deterministic business data, compares the invoice against the PO, checks for duplicates, and returns a structured decision with a full tool trace.

The goal is to demonstrate:

- A real multi-step tool-calling loop where later calls depend on earlier results.
- Structured extraction that preserves uncertainty and never fabricates values.
- Deterministic business validation (vendor, PO, matching, duplicate detection).
- Graceful degradation on blurry, blank, or partial documents.
- Clean agent termination with explicit final statuses.
- Optional LLM orchestration layer that selects tools while deterministic tools remain the source of truth.

## 2. Why invoice intake / AP triage

Invoice processing is a repetitive, high-volume business workflow where:

- A single bad number can cause duplicate payments or missed discounts.
- Missing PO numbers or mismatched totals must be routed to humans.
- Documents vary wildly in quality (scanned, blurry, cropped, rotated).
- Business facts (vendor IDs, PO amounts, expected totals) must come from authoritative systems, not from guessing.

This makes it an ideal domain for evaluating tool-grounded agents.

## 3. Workflow

```text
Invoice document
       ↓
inspect_document
       ↓
extract_invoice
       ↓
lookup_vendor
       ↓
lookup_purchase_order   (only if PO number was extracted)
       ↓
match_invoice_to_po     (only if PO was found)
       ↓
check_duplicate_invoice (only if vendor was resolved)
       ↓
final decision
```

The exact sequence depends on tool results. For example:

- If inspection reports `NO_TEXT_DETECTED` → stop, return `NEEDS_REVIEW`.
- If extraction returns no PO number → skip `lookup_purchase_order`, return `NEEDS_REVIEW`.
- If vendor lookup returns `AMBIGUOUS` → do not select a vendor, return `NEEDS_REVIEW`.

## 4. Architecture

```text
app/
├── agent/
│   ├── orchestrator.py    # Deterministic state machine (InvoiceAgent)
│   ├── llm_orchestrator.py # LLM-driven orchestration (LLMInvoiceAgent)
│   ├── llm_client.py      # LLM client wrapper with mock support
│   ├── state.py           # State helpers (terminal state, next step)
│   ├── prompts.py         # System prompt for the agent
│   ├── tool_schemas.py    # Tool definitions for LLM function calling
│   └── validators.py      # Argument and final-decision validators
├── tools/
│   ├── document.py        # inspect_document
│   ├── extraction.py      # extract_invoice (PDF text + regex parsing)
│   ├── vendor.py          # lookup_vendor
│   ├── purchase_order.py  # lookup_purchase_order
│   ├── matching.py        # match_invoice_to_po
│   ├── duplicate.py       # check_duplicate_invoice
│   └── runner.py          # Shared tool execution logic
├── models/
│   ├── invoice.py         # ExtractedInvoice, InvoiceField, CurrencyValue, etc.
│   ├── tool_result.py     # AgentState, ToolResult
│   └── decision.py        # DecisionResult, MatchResult, ExceptionCode, etc.
├── data/
│   ├── vendors.json
│   ├── purchase_orders.json
│   └── processed_invoices.json
├── api/
│   └── routes.py          # FastAPI endpoint
└── main.py                # App factory
```

## 5. Agent / tool loop

Two modes are available:

### Deterministic mode (default)

`InvoiceAgent` maintains an explicit `AgentState` and executes tools one at a time:

1. **inspect_document** — determines format, page count, readability, text availability, and quality flags.
2. **extract_invoice** — extracts structured fields with confidence/status from PDF text using deterministic regex.
3. **lookup_vendor** — matches the extracted vendor name against fixture data.
4. **lookup_purchase_order** — retrieves PO details using the extracted PO number.
5. **match_invoice_to_po** — deterministic comparison of vendor, currency, line items, quantities, unit prices, and totals.
6. **check_duplicate_invoice** — checks vendor ID + invoice number against processed invoices.

### LLM mode

`LLMInvoiceAgent` wraps the same deterministic tools. The LLM acts as an orchestrator that:

- Observes the document and extracted fields.
- Decides which tool to call next.
- Receives structured tool results.
- Decides whether more evidence is required or if a final decision can be made.

The LLM never becomes the source of truth for business facts. All invoice totals, vendor IDs, PO amounts, and match results come from deterministic tools.

```text
User
  ↓
LLM InvoiceAgent
  ↓
LLM tool selection (function calling)
  ↓
Existing deterministic tool
  ↓
Structured tool result
  ↓
LLM observes result
  ↓
Next tool OR final decision
```

## 6. Extraction schema

Every extracted field is represented as:

```json
{
  "value": "INV-1042",
  "confidence": 0.98,
  "status": "FOUND",
  "source_page": 1,
  "source_text": "Invoice No: INV-1042"
}
```

Supported statuses:

- `FOUND` — value extracted with high confidence.
- `MISSING` — field not present in the document.
- `UNCERTAIN` — value inferred or derived, not directly extracted.
- `UNREADABLE` — document quality prevented reliable extraction.
- `CONFLICTING` — multiple candidate values were found.

Confidence represents parser certainty, not OCR probability.

## 7. Tool contracts

### inspect_document(document_path)

Returns:

```json
{
  "supported": true,
  "page_count": 1,
  "readable": true,
  "text_detected": true,
  "quality_flags": [],
  "file_type": "pdf",
  "file_size_bytes": 1234
}
```

### extract_invoice(document_path, inspection?)

Returns `ExtractedInvoice` with all required fields.

### lookup_vendor(name, tax_id?)

Returns:

```json
{
  "status": "UNIQUE",
  "matches": [{ "vendor_id": "V-101", "name": "...", "tax_id": "..." }]
}
```

Statuses: `UNIQUE`, `NONE`, `AMBIGUOUS`.

### lookup_purchase_order(po_number)

Returns:

```json
{
  "status": "FOUND",
  "po_number": "PO-88021",
  "vendor_id": "V-101",
  "currency": "USD",
  "status": "OPEN",
  "line_items": [...],
  "expected_total": 1250.00
}
```

### match_invoice_to_po(extraction, po_data, vendor_matches?)

Returns `MatchResult` with explicit checks:

```json
{
  "overall": "PASS",
  "checks": {
    "vendor_match": "PASS",
    "po_number_match": "PASS",
    "currency_match": "PASS",
    "line_items_match": "PASS",
    "quantity_match": "PASS",
    "unit_price_match": "PASS",
    "total_match": "PASS"
  },
  "exceptions": []
}
```

### check_duplicate_invoice(vendor_id, invoice_number)

Returns:

```json
{
  "duplicate": false,
  "matches": []
}
```

## 8. No-hallucination behavior

The system never invents:

- invoice numbers
- vendor names or IDs
- PO numbers or amounts
- totals, tax, or quantities
- duplicate records

If a value cannot be reliably extracted or looked up, the field returns `null` with status `MISSING`, `UNREADABLE`, or `UNCERTAIN`. The agent explains what prevented reliable processing in the final message.

### LLM argument validation

Before any tool is executed, arguments are validated against the current agent state:

- `lookup_purchase_order` cannot be called with a PO number that does not match the extracted value.
- `lookup_vendor` cannot be called with a name that does not match the extracted value.
- `match_invoice_to_po` cannot be called without successful PO data.
- `check_duplicate_invoice` cannot be called without a uniquely resolved vendor.

If validation fails, the tool call is rejected with a structured error and the agent terminates or chooses an alternative.

### Final decision validator

Before returning the final result, a deterministic validator enforces:

- If the document is unreadable → cannot return `READY_FOR_REVIEW`
- If the vendor is ambiguous → cannot return `READY_FOR_REVIEW`
- If PO mismatch exists → cannot return `READY_FOR_REVIEW`
- If duplicate exists → cannot return `READY_FOR_REVIEW`
- If required evidence is missing → cannot return `READY_FOR_REVIEW`

This protects the system from LLM mistakes.

## 9. Error handling

All tools return structured results. If a tool raises an unexpected exception, the agent catches it and returns `NEEDS_REVIEW` with `TOOL_FAILURE`. Raw tracebacks are never exposed to the API consumer.

## 10. Dataset / fixture structure

Local fixture files in `app/data/`:

- `vendors.json` — 5 vendors, including ambiguous duplicates.
- `purchase_orders.json` — 4 POs with varying totals and vendors.
- `processed_invoices.json` — 4 processed invoices including one duplicate pair.

Test fixtures in `tests/fixtures/`:

- `clean_invoice_01.pdf` — clean invoice with PO (duplicate).
- `clean_invoice_02.pdf` — second clean invoice.
- `clean_invoice_03.pdf` — clean invoice for READY_FOR_REVIEW demo.
- `blurry_invoice.png` — image without OCR (simulates scanned doc).
- `blank_invoice.pdf` — empty document.
- `partial_invoice.pdf` — cropped document with missing totals.
- `rotated_invoice.pdf` — rotated text layout.
- `wrong_total_invoice.pdf` — invoice with mismatched total.

## 11. How to install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 12. How to configure environment variables

Copy `.env.example` to `.env` and set values as needed. No API keys are required for the core functionality (all business data is local fixture data).

```bash
cp .env.example .env
```

Set `AGENT_MODE` to control orchestration:

- `deterministic` — uses the built-in state machine (default, no API key needed).
- `llm` — uses an LLM for tool selection (requires `OPENAI_API_KEY`).

## 13. How to run

### API (FastAPI)

```bash
python -m app.main
# or
uvicorn app.main:app --reload
```

Send a request:

```bash
curl -X POST "http://localhost:8000/process-invoice" -F "file=@invoice.pdf"
```

With LLM mode:

```bash
curl -X POST "http://localhost:8000/process-invoice?mode=llm" -F "file=@invoice.pdf"
```

### CLI

```bash
python -m app.cli path/to/invoice.pdf
python -m app.cli path/to/invoice.pdf --instruction "Check this." --json
python -m app.cli path/to/invoice.pdf --mode llm
```

## 14. How to run tests

```bash
python -m pytest tests/ -v
```

All tests run offline without requiring an LLM API key.

## 15. Example successful workflow

```text
Upload clean_invoice_03.pdf
       ↓
inspect_document → supported=true, readable=true
       ↓
extract_invoice → INV-8888, PO-88021, total=1250.00
       ↓
lookup_vendor → UNIQUE (V-101 Acme Supplies Pvt Ltd)
       ↓
lookup_purchase_order → FOUND PO-88021, expected_total=1250.00
       ↓
match_invoice_to_po → overall=PASS
       ↓
check_duplicate_invoice → duplicate=false
       ↓
READY_FOR_REVIEW
```

Tool trace:

```text
1. inspect_document
2. extract_invoice
3. lookup_vendor
4. lookup_purchase_order
5. match_invoice_to_po
6. check_duplicate_invoice
7. final decision
```

## 16. Example blurry-document workflow

```text
Upload blurry_invoice.png
       ↓
inspect_document → NO_TEXT_DETECTED
       ↓
NEEDS_REVIEW
       ↓
Message: "No text detected; document may be scanned without OCR."
```

## 17. Example mismatch workflow

```text
Upload wrong_total_invoice.pdf
       ↓
inspect_document → readable
       ↓
extract_invoice → INV-9999, PO-88024, total=1750.00
       ↓
lookup_vendor → UNIQUE (V-104 Beta Logistics Ltd)
       ↓
lookup_purchase_order → FOUND PO-88024, expected_total=1500.00
       ↓
match_invoice_to_po → overall=FAIL, TOTAL_MISMATCH
       ↓
NEEDS_REVIEW
```

## 18. Example LLM orchestration workflow

```text
User uploads invoice
       ↓
LLM decides: call inspect_document
       ↓
Tool result: supported=true, readable=true
       ↓
LLM decides: call extract_invoice
       ↓
Tool result: PO-88021 extracted
       ↓
LLM decides: call lookup_purchase_order with PO-88021
       ↓
Validator checks: PO-88021 matches extracted value
       ↓
Tool result: PO found, expected_total=1250.00
       ↓
LLM decides: call match_invoice_to_po
       ↓
Tool result: overall=PASS
       ↓
LLM decides: final decision READY_FOR_REVIEW
       ↓
Validator checks: no mismatches, no duplicates
       ↓
READY_FOR_REVIEW
```

## 19. Example LLM hallucination attempt

```text
LLM attempts: lookup_purchase_order("PO-FAKE")
       ↓
Validator checks: extracted po_number = null
       ↓
Rejected: UNSUPPORTED_TOOL_ARGUMENT
       ↓
Agent terminates: NEEDS_REVIEW
```

## 20. Example LLM override attempt

```text
match_invoice_to_po → TOTAL_MISMATCH
       ↓
LLM attempts: final decision READY_FOR_REVIEW
       ↓
Validator checks: deterministic mismatch exists
       ↓
Overridden: NEEDS_REVIEW
```

## 21. Known limitations

- OCR requires Tesseract to be installed separately. Images without a text layer are treated as `NO_TEXT_DETECTED`.
- The extraction layer uses regex-based parsing. It works reliably for well-formatted invoices but may miss fields on heavily stylized documents.
- Business data is stored in local JSON fixtures. In production, vendor and PO lookups would query an ERP.
- The deterministic mode is fully offline and reproducible. The LLM mode requires an OpenAI-compatible API key.

## 22. License

MIT
