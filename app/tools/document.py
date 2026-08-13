"""Document inspection tool."""

import os
from pathlib import Path
from typing import List, Optional

import pdfplumber

from app.models.invoice import DocumentInspection


def inspect_document(document_path: str) -> DocumentInspection:
    path = Path(document_path)
    if not path.exists():
        return DocumentInspection(
            supported=False,
            readable=False,
            text_detected=False,
            quality_flags=["UNSUPPORTED_FORMAT"],
            file_type="unknown",
            file_size_bytes=0,
        )

    suffix = path.suffix.lower()
    supported_exts = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}
    supported = suffix in supported_exts

    file_size_bytes = os.path.getsize(document_path)
    file_type = suffix.lstrip(".") if supported else None

    flags: List[str] = []
    page_count = 1
    readable = True
    text_detected = False

    if not supported:
        flags.append("UNSUPPORTED_FORMAT")
        return DocumentInspection(
            supported=False,
            page_count=0,
            readable=False,
            text_detected=False,
            quality_flags=flags,
            file_type=suffix.lstrip("."),
            file_size_bytes=file_size_bytes,
        )

    try:
        if suffix == ".pdf":
            with pdfplumber.open(document_path) as pdf:
                page_count = len(pdf.pages)
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""
            text_detected = bool(text.strip())
            if page_count == 0:
                flags.append("EMPTY_DOCUMENT")
            if not text_detected:
                flags.append("NO_TEXT_DETECTED")
                readable = False
        else:
            from PIL import Image

            img = Image.open(document_path)
            width, height = img.size
            if width == 0 or height == 0:
                flags.append("EMPTY_DOCUMENT")
                readable = False
            else:
                import numpy as np

                arr = np.array(img.convert("L"))
                std = arr.std()
                if std < 15:
                    flags.append("LOW_CONTRAST")
                if std < 8:
                    flags.append("BLURRY")
                    readable = False
                if width != height and abs(width - height) > max(width, height) * 0.5:
                    flags.append("ROTATED")
                text_detected = True
    except Exception:
        flags.append("UNREADABLE_DOCUMENT")
        readable = False
        text_detected = False

    if not text_detected and "NO_TEXT_DETECTED" not in flags:
        flags.append("NO_TEXT_DETECTED")
        readable = False

    return DocumentInspection(
        supported=supported,
        page_count=page_count,
        readable=readable,
        text_detected=text_detected,
        quality_flags=flags,
        file_type=file_type,
        file_size_bytes=file_size_bytes,
    )
