"""Run on the GPU host (Kaggle / university server / cloud GPU), from the folder that contains gpu_service/:

    GPU_API_KEY=... HANDOFF_DIR=/path/to/handoff uvicorn gpu_service.server:app --host 0.0.0.0 --port 8000 --workers 1

HANDOFF_DIR must contain the report's section 12.1 files:
    advice_catalog.json, ecowatt_system_prompt.txt, ecowatt_safety_rules.json, ecowatt_required_prefixes.json
Use exactly ONE worker: the model is loaded once into GPU memory.
"""
from __future__ import annotations

import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .service import EngineService, GpuBusy, ModelOutputError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class GenerateIn(BaseModel):
    profile: dict
    period: dict
    analysis: dict
    exclude_ids: list[str] = []


def _load_ocr():
    """The original invoice_ocr (copy of app/invoice_ocr.py); EasyOCR picks the GPU automatically."""
    try:
        from .invoice_ocr import analyze_bill
        return analyze_bill
    except Exception as e:                       # easyocr missing -> advice still works, scanning stays on the backend
        logging.getLogger("ecowatt.gpu").warning("OCR disabled on the GPU host: %s", e)
        return None


def create_app(service: EngineService | None = None) -> FastAPI:
    api_key = os.getenv("GPU_API_KEY", "").strip()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not api_key:
            raise RuntimeError("GPU_API_KEY is required: the endpoint is reachable from the internet.")
        if service is None:
            from .advice_engine import AdviceEngine          # heavy imports (torch, transformers) happen only here
            handoff = Path(os.getenv("HANDOFF_DIR", Path(__file__).resolve().parent / "handoff"))
            app.state.service = EngineService(AdviceEngine(base_dir=str(handoff)), handoff, ocr=_load_ocr())
        else:
            app.state.service = service
        yield

    app = FastAPI(title="EcoWatt GPU service", lifespan=lifespan)

    def require_key(authorization: str = Header(default="")):
        token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(token, api_key):
            raise HTTPException(401, "Invalid API key")

    @app.get("/health")
    async def health():
        return app.state.service.health()

    @app.post("/generate", dependencies=[Depends(require_key)])
    async def generate(body: GenerateIn):
        try:
            return await app.state.service.generate(body.profile, body.period, body.analysis, body.exclude_ids)
        except ModelOutputError as e:
            return JSONResponse(status_code=422, content={"error": "model_invalid_output", "detail": str(e)})
        except GpuBusy as e:
            return JSONResponse(status_code=503, content={"error": "gpu_out_of_memory", "detail": str(e)})

    @app.post("/ocr", dependencies=[Depends(require_key)])
    async def ocr(file: UploadFile = File(...)):
        data = await file.read(10 * 1024 * 1024 + 1)
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(413, "Image is larger than 10 MB.")
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            suffix = ".png"
        elif data.startswith(b"\xff\xd8\xff"):
            suffix = ".jpg"
        else:
            raise HTTPException(400, "Please upload a valid JPG or PNG image.")
        try:
            return await app.state.service.scan_bill(data, suffix)
        except RuntimeError as e:
            raise HTTPException(503, str(e))

    return app


app = create_app() if os.getenv("GPU_SERVICE_AUTOSTART", "1") == "1" else None
