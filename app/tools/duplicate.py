"""Duplicate invoice detection tool."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "processed_invoices.json"


def _load_processed() -> list:
    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def check_duplicate_invoice(
    vendor_id: Optional[str], invoice_number: Optional[str], invoice_date: Optional[str] = None
) -> Dict[str, Any]:
    if not vendor_id or not invoice_number:
        return {"duplicate": False, "matches": []}
    processed = _load_processed()
    matches = []
    for rec in processed:
        if (
            rec.get("vendor_id", "").upper() == vendor_id.upper()
            and rec.get("invoice_id", "").upper() == invoice_number.upper()
        ):
            matches.append(rec)
    return {"duplicate": len(matches) > 0, "matches": matches}
