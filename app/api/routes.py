"""FastAPI application factory and routes."""

import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.agent.llm_client import get_llm_client
from app.agent.llm_orchestrator import LLMInvoiceAgent
from app.agent.orchestrator import InvoiceAgent
from app.models.decision import DecisionResult


def create_app(agent: Optional[object] = None) -> FastAPI:
    app = FastAPI(title="Invoice Intake Agent", version="0.2.0")
    app.state.agent = agent

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/process-invoice", response_model=DecisionResult)
    async def process_invoice(
        file: UploadFile = File(...),
        instruction: Optional[str] = None,
        mode: Optional[str] = None,
    ):
        allowed = {"pdf", "png", "jpg", "jpeg", "tiff", "tif", "bmp"}
        ext = Path(file.filename).suffix.lower().lstrip(".")
        if ext not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

        upload_dir = Path(os.environ.get("UPLOAD_DIR", "/tmp/kilo-invoices"))
        upload_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        dest = upload_dir / unique_name

        try:
            content = await file.read()
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="File too large (max 20MB).")
            dest.write_bytes(content)

            agent_mode = mode or os.environ.get("AGENT_MODE", "deterministic")
            if app.state.agent is None:
                if agent_mode == "llm":
                    llm_client = get_llm_client("llm")
                    app.state.agent = LLMInvoiceAgent(llm_client=llm_client)
                else:
                    app.state.agent = InvoiceAgent()

            result = app.state.agent.process(str(dest), instruction)
            return result
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            if dest.exists():
                try:
                    dest.unlink()
                except OSError:
                    pass

    return app
