"""Bill OCR endpoint (POST /analyze-bill), merged into the main API so Flutter needs ONE base URL.

Where the scan runs:
  1. on the GPU host (gpu_service /ocr, EasyOCR with CUDA): a few seconds
  2. fallback, if the GPU host is unreachable: here on the CPU, if easyocr/opencv/torch are installed
     (requirements-ocr.txt) - correct but slow (minutes on a laptop CPU)
Both run the original invoice_ocr.analyze_bill (same file on both sides) and return the same JSON. invoice_ocr's
kWh extraction was extended (see tests/test_invoice_ocr.py): the number right after a label is also tried on its
own, a label without a value falls through to the next matching line, and the meter-reading difference is used.
Differences from the original backend/api.py: requires the user's Supabase session, 10 MB upload limit,
blocking OCR runs in a worker thread.
"""
from __future__ import annotations

import logging
import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from .auth import current_user

router = APIRouter()
log = logging.getLogger("ecowatt.ocr")
MAX_BYTES = 10 * 1024 * 1024
_local = {"fn": None, "error": None}


def _local_analyze():
    """Import the CPU OCR lazily (loading EasyOCR takes ~30 s and ~300 MB of models)."""
    if _local["fn"] is None and _local["error"] is None:
        try:
            from .invoice_ocr import analyze_bill
            _local["fn"] = analyze_bill
        except Exception as e:                       # libraries not installed
            _local["error"] = str(e)
    return _local["fn"]


@router.post("/analyze-bill")
async def analyze_bill_endpoint(request: Request, file: UploadFile = File(...), user: dict = Depends(current_user)):
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image is larger than 10 MB.")
    is_png = data.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = data.startswith(b"\xff\xd8\xff")
    if not (is_png or is_jpeg):
        raise HTTPException(400, "Please upload a valid JPG or PNG image.")

    gpu = request.app.state.llm
    if hasattr(gpu, "ocr"):
        try:
            result = await gpu.ocr(data, file.filename or ("bill.png" if is_png else "bill.jpg"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        if result is not None:
            return result
        log.info("GPU OCR unavailable, scanning on the CPU")

    analyze = await run_in_threadpool(_local_analyze)
    if analyze is None:
        raise HTTPException(503, "Bill scanning is not available right now. Please enter the bill details manually.")
    path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png" if is_png else ".jpg") as tmp:
            tmp.write(data)
            path = tmp.name
        return await run_in_threadpool(analyze, path)
    except Exception as e:
        raise HTTPException(500, f"Failed to analyze bill: {e}")
    finally:
        if path and os.path.exists(path):
            os.remove(path)
