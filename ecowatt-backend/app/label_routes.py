"""AC energy-label scanning (POST /analyze-ac-label). Shows results only: nothing is stored.

Runs on the backend's CPU with PaddleOCR's mobile models (requirements-label.txt). If PaddleOCR is not
installed, the endpoint answers 503 with a readable message and the rest of the API is unaffected.
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
import logging
import threading
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from .auth import current_user

router = APIRouter()
MAX_BYTES = 10 * 1024 * 1024
log = logging.getLogger("ecowatt.label")
_lock = threading.Lock()            # the PaddleOCR engine is shared and not thread-safe: one scan at a time


def _suffix(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def warm_up() -> None:
    """Load the OCR engine in the background at startup (~10 s), so the first scan is not slower."""
    if importlib.util.find_spec("paddleocr") is None:
        return

    def load():
        try:
            from .label_ocr import get_ocr_engine
            with _lock:
                get_ocr_engine()
        except Exception:
            pass                                    # the endpoint reports the problem when a label is scanned

    threading.Thread(target=load, daemon=True).start()


def _scan(path: str) -> dict:
    from .label_ocr import analyze_label        # loads OpenCV/PaddleOCR only when a label is scanned
    with _lock:
        start = time.monotonic()
        result = analyze_label(path)
        log.info("AC label scanned in %.1f s", time.monotonic() - start)
        return result


@router.post("/analyze-ac-label")
async def analyze_ac_label(file: UploadFile = File(...), user: dict = Depends(current_user)):
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image is larger than 10 MB.")
    suffix = _suffix(data)
    if suffix is None:
        raise HTTPException(400, "Please upload a JPG, PNG or WEBP photo of the energy label.")
    if importlib.util.find_spec("paddleocr") is None:
        raise HTTPException(503, "AC label scanning is not available on this server right now.")

    path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            path = tmp.name
        return await run_in_threadpool(_scan, path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Could not read the label: {e}")
    finally:
        if path and os.path.exists(path):
            os.remove(path)
