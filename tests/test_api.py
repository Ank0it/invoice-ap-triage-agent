"""Tests for API routes."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.api.routes import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestAPI:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_process_invoice_clean(self, client, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.png")
        with open(p, "rb") as f:
            resp = client.post("/process-invoice", files={"file": ("clean.png", f, "image/png")})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in {"READY_FOR_REVIEW", "NEEDS_REVIEW"}

    def test_process_invoice_unsupported_format(self, client):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            f.write(b"notarealfile")
            path = f.name
        try:
            with open(path, "rb") as fh:
                resp = client.post("/process-invoice", files={"file": ("bad.exe", fh, "application/octet-stream")})
            assert resp.status_code == 400
        finally:
            os.unlink(path)

    def test_process_invoice_with_instruction(self, client, tmp_path):
        from tests.fixtures.generator import generate_clean_invoice_01
        p = generate_clean_invoice_01(tmp_path / "clean.png")
        with open(p, "rb") as f:
            resp = client.post(
                "/process-invoice",
                files={"file": ("clean.png", f, "image/png")},
                data={"instruction": "Check this."},
            )
        assert resp.status_code == 200
