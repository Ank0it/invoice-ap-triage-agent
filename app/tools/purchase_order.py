"""Purchase order lookup tool using deterministic fixture data."""

import json
from pathlib import Path
from typing import Optional

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "purchase_orders.json"


def _load_pos() -> list:
    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def lookup_purchase_order(po_number: str) -> dict:
    if not po_number:
        return {"status": "NOT_FOUND"}
    for po in _load_pos():
        if po.get("po_number", "").strip().upper() == po_number.strip().upper():
            result = dict(po)
            result["status"] = "FOUND"
            return result
    return {"status": "NOT_FOUND"}
