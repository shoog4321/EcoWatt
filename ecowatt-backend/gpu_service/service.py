"""GPU-side wrapper around the original AdviceEngine (advice_engine.py, copied UNCHANGED).

Why a wrapper: AdviceEngine.generate_advice() is blocking and the model lives on one GPU, so a web server needs
  * a lock (one generation at a time),
  * a worker thread (so /health stays responsive while the GPU is busy),
  * per-request exclusions: the backend sends ids the model must not pick (already applied, purchases the
    household declined, off-season); they are hidden from the engine's catalog for that one request,
  * a defensive strip of personal data (the engine would copy `first_name` into the prompt, but the evaluation
    ran WITHOUT names - the backend adds the first name after generation).
No fastapi/torch import here, so this logic is unit-testable anywhere.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

log = logging.getLogger("ecowatt.gpu")

HANDOFF_FILES = {
    "catalog_sha256": "advice_catalog.json",
    "prompt_sha256": "ecowatt_system_prompt.txt",
    "safety_rules_sha256": "ecowatt_safety_rules.json",
    "prefixes_sha256": "ecowatt_required_prefixes.json",
}
PERSONAL_KEYS = {"first_name", "last_name", "firstname", "lastname", "name", "email", "phone", "phonenum",
                 "user_id", "id", "household_id"}


MIN_ADVICE = 3


class ModelOutputError(RuntimeError):
    """The model produced output the engine could not use (invalid JSON etc.). Deterministic: do not retry."""


class GpuBusy(RuntimeError):
    """Out of GPU memory. Transient: the caller may retry later."""


def file_hashes(directory: Path) -> dict[str, str | None]:
    out = {}
    for key, name in HANDOFF_FILES.items():
        p = Path(directory) / name
        out[key] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    return out


def strip_personal(profile: dict) -> dict:
    return {k: v for k, v in profile.items() if str(k).lower() not in PERSONAL_KEYS}


class EngineService:
    def __init__(self, engine, handoff_dir: Path, ocr=None):
        self.engine = engine
        self.hashes = file_hashes(handoff_dir)
        self._lock = asyncio.Lock()
        self.ocr = ocr                     # callable(image_path) -> dict (invoice_ocr.analyze_bill), or None
        self._ocr_lock = asyncio.Lock()    # separate: a bill scan must not wait behind a 1-minute advice job

    def health(self) -> dict:
        return {"status": "ok", "model": getattr(self.engine, "model_id", "unknown"),
                "ocr": self.ocr is not None, **self.hashes}

    async def scan_bill(self, data: bytes, suffix: str) -> dict:
        """Runs the original invoice_ocr.analyze_bill on the GPU (EasyOCR with CUDA)."""
        if self.ocr is None:
            raise RuntimeError("OCR is not available on this GPU host (easyocr not installed).")
        import os
        import tempfile
        path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(data)
                path = tmp.name
            async with self._ocr_lock:
                return await asyncio.to_thread(self.ocr, path)
        finally:
            if path and os.path.exists(path):
                os.remove(path)

    def _generate(self, profile: dict, period: dict, analysis: dict, exclude: set[str]) -> list[dict]:
        """Runs under the lock, so swapping the engine's catalog cannot affect another request."""
        full = getattr(self.engine, "catalog", None)
        if exclude and isinstance(full, list):
            kept = [a for a in full if a.get("advice_id") not in exclude]
            if len(kept) >= MIN_ADVICE:
                self.engine.catalog = kept
        try:
            return self.engine.generate_advice(profile, period, analysis)
        finally:
            if full is not None:
                self.engine.catalog = full

    async def generate(self, profile: dict, period: dict, analysis: dict,
                       exclude_ids: list[str] | None = None) -> dict:
        clean = strip_personal(profile)
        async with self._lock:                                   # one generation at a time on the GPU
            try:
                advice = await asyncio.to_thread(self._generate, clean, period, analysis, set(exclude_ids or []))
            except ValueError as e:                              # engine raises ValueError on invalid JSON
                raise ModelOutputError(str(e)) from e
            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    self._free_cuda()
                    raise GpuBusy(str(e)) from e
                raise
        audit = [{"advice_id": a["advice_id"], "safe": bool(self.engine._safe(a["advice_id"], a["personalized_advice"]))}
                 for a in advice]
        return {"advice": advice, "audit": audit, **self.hashes}

    @staticmethod
    def _free_cuda() -> None:
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
