"""Vendor lookup tool using deterministic fixture data."""

import json
from pathlib import Path
from typing import List, Optional

from app.models.invoice import InvoiceField


_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "vendors.json"


def _load_vendors() -> List[dict]:
    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def lookup_vendor(name: str, tax_id: Optional[str] = None) -> dict:
    vendors = _load_vendors()
    name_lower = name.strip().lower()
    matches = []
    for v in vendors:
        vname = v.get("name", "").lower()
        if name_lower in vname or vname in name_lower:
            if tax_id and v.get("tax_id", "").upper() != tax_id.strip().upper():
                continue
            matches.append(v)

    if len(matches) == 0:
        return {"status": "NONE", "matches": []}
    if len(matches) == 1:
        return {"status": "UNIQUE", "matches": matches}
    return {"status": "AMBIGUOUS", "matches": matches}
