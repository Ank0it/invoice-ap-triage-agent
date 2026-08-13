"""Test fixture generator for deterministic documents."""

import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from fpdf import FPDF

FIXTURE_DIR = Path(__file__).resolve().parent
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)


def _write_text_image(path: Path, text: str, size=(800, 600), color=(0, 0, 0), bg=(255, 255, 255)):
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        font = ImageFont.load_default()
    draw.text((20, 20), text, fill=color, font=font)
    img.save(path)


def _generate_pdf(path: Path, lines: list):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10)
    for line in lines:
        pdf.cell(0, 6, line)
        pdf.ln()
    pdf.output(str(path))


def generate_clean_invoice_01(path: Optional[Path] = None) -> Path:
    path = path or FIXTURE_DIR / "clean_invoice_01.pdf"
    _generate_pdf(path, [
        "Invoice Number: INV-1042",
        "Invoice Date: 2024-05-15",
        "Due Date: 2024-06-15",
        "From: Acme Supplies Pvt Ltd",
        "GST: GST-123",
        "PO Number: PO-88021",
        "Payment Terms: Net 30",
        "Subtotal: $1,050.00",
        "Tax: $200.00",
        "Shipping: $0.00",
        "Total: $1,250.00",
        "Amount Due: $1,250.00",
        "Currency: USD",
        "Line Items:",
        "1. Industrial Bearings   x5  $100.00  $500.00",
        "2. Hydraulic Seals        x10 $25.00   $250.00",
        "3. Steel Shafts           x2  $75.00   $150.00",
    ])
    return path


def generate_clean_invoice_02(path: Optional[Path] = None) -> Path:
    path = path or FIXTURE_DIR / "clean_invoice_02.pdf"
    _generate_pdf(path, [
        "Invoice Number: INV-5555",
        "Invoice Date: 2024-07-01",
        "Due Date: 2024-08-01",
        "From: Beta Logistics Ltd",
        "GST: GST-321",
        "PO Number: PO-88024",
        "Payment Terms: Net 45",
        "Subtotal: $1,350.00",
        "Tax: $150.00",
        "Shipping: $0.00",
        "Total: $1,500.00",
        "Amount Due: $1,500.00",
        "Currency: USD",
        "Line Items:",
        "1. Packaging Tape  x100 $15.00  $1,500.00",
    ])
    return path


def generate_blurry_invoice(path: Optional[Path] = None) -> Path:
    path = path or FIXTURE_DIR / "blurry_invoice.png"
    _write_text_image(path, """
INVOICE
Invoice Number: INV-XXXX
Invoice Date: 2024-05-15
From: Acme Supplies Pvt Ltd
PO Number: PO-88021
Total: $1,250.00
Currency: USD
""", size=(400, 300))
    return path


def generate_blank_invoice(path: Optional[Path] = None) -> Path:
    path = path or FIXTURE_DIR / "blank_invoice.pdf"
    _generate_pdf(path, [])
    return path


def generate_partial_invoice(path: Optional[Path] = None) -> Path:
    path = path or FIXTURE_DIR / "partial_invoice.pdf"
    _generate_pdf(path, [
        "Invoice Number: INV-2049",
        "Invoice Date: 2024-05-15",
        "Due Date: 2024-06-15",
        "From: Acme Supplies Pvt Ltd",
    ])
    return path


def generate_rotated_invoice(path: Optional[Path] = None) -> Path:
    path = path or FIXTURE_DIR / "rotated_invoice.pdf"
    _generate_pdf(path, [
        "Invoice Number: INV-3001",
        "Invoice Date: 2024-05-15",
        "Due Date: 2024-06-15",
        "From: Acme Supplies Pvt Ltd",
        "GST: GST-123",
        "PO Number: PO-88021",
        "Total: $1,250.00",
        "Currency: USD",
    ])
    return path


def generate_wrong_total_invoice(path: Optional[Path] = None) -> Path:
    path = path or FIXTURE_DIR / "wrong_total_invoice.pdf"
    _generate_pdf(path, [
        "Invoice Number: INV-9999",
        "Invoice Date: 2024-05-15",
        "Due Date: 2024-06-15",
        "From: Beta Logistics Ltd",
        "GST: GST-321",
        "PO Number: PO-88024",
        "Payment Terms: Net 30",
        "Subtotal: $1,350.00",
        "Tax: $150.00",
        "Shipping: $0.00",
        "Total: $1,750.00",
        "Amount Due: $1,750.00",
        "Currency: USD",
        "Line Items:",
        "1. Packaging Tape  x100 $15.00  $1,500.00",
    ])
    return path


def generate_low_contrast_invoice(path: Optional[Path] = None) -> Path:
    path = path or FIXTURE_DIR / "low_contrast_invoice.pdf"
    _generate_pdf(path, [" "])
    return path


def generate_clean_invoice_03(path: Optional[Path] = None) -> Path:
    path = path or FIXTURE_DIR / "clean_invoice_03.pdf"
    _generate_pdf(path, [
        "Invoice Number: INV-8888",
        "Invoice Date: 2024-08-01",
        "Due Date: 2024-09-01",
        "From: Acme Supplies Pvt Ltd",
        "GST: GST-123",
        "PO Number: PO-88021",
        "Payment Terms: Net 30",
        "Subtotal: $1,050.00",
        "Tax: $200.00",
        "Shipping: $0.00",
        "Total: $1,250.00",
        "Amount Due: $1,250.00",
        "Currency: USD",
        "Line Items:",
        "1. Industrial Bearings   x5  $100.00  $500.00",
        "2. Hydraulic Seals        x10 $25.00   $250.00",
        "3. Steel Shafts           x2  $75.00   $150.00",
    ])
    return path


def generate_all_fixtures():
    generate_clean_invoice_01()
    generate_clean_invoice_02()
    generate_blurry_invoice()
    generate_blank_invoice()
    generate_partial_invoice()
    generate_rotated_invoice()
    generate_wrong_total_invoice()
    generate_low_contrast_invoice()
