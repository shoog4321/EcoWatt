"""EcoWatt application layer (report 4.3.1): FastAPI between Flutter, Supabase and the GPU.

Flutter flow:  save the bill in Supabase (as today) -> POST /bills/{id}/analyze
               -> read advice_jobs.status (poll or Realtime) -> read Advice rows (existing RLS) or GET /bills/{id}/advice
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import bills, rule_engine
from . import db as D
from .advice_engine import AdviceEngine, load_catalog
from .auth import current_user
from .config import load_settings
from .gpu_client import GpuClient
from .jobs import AdviceJobs
from .llm_client import LLMClient
from .remote_engine import RemoteAdviceEngine
from .safety import SafetyRules

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = load_settings()
    http = httpx.AsyncClient()
    catalog_file = s.data_dir / "advice_catalog.json"
    catalog = load_catalog(catalog_file)
    if s.engine_mode == "gpu_service":
        # The original AdviceEngine runs on the GPU host; prompt + safety rules live there.
        client = GpuClient(http, s)
        engine = RemoteAdviceEngine(client, catalog, hashlib.sha256(catalog_file.read_bytes()).hexdigest())
    elif s.engine_mode == "openai":
        # Alternative: vLLM (OpenAI-compatible). Prompt + safety layer run in THIS process.
        prompt_file = s.data_dir / "system_prompt.txt"
        if not prompt_file.exists():
            raise RuntimeError(f"Missing {prompt_file}: copy ecowatt_system_prompt.txt from the handoff package.")
        client = LLMClient(http, s)
        engine = AdviceEngine(client, catalog, prompt_file.read_text(encoding="utf-8"), SafetyRules.load(s.data_dir))
    else:
        raise RuntimeError(f"ENGINE_MODE must be 'gpu_service' or 'openai', got {s.engine_mode!r}")
    jobs = AdviceJobs(D.Db(http, s), engine)
    app.state.settings, app.state.http, app.state.llm, app.state.jobs = s, http, client, jobs
    app.state.db, app.state.baselines = jobs.db, None
    sweeper = asyncio.create_task(jobs.sweeper())
    label_routes.warm_up()
    yield
    sweeper.cancel()
    await http.aclose()


app = FastAPI(title="EcoWatt API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()],
    allow_methods=["*"], allow_headers=["*"],
)
from .ocr_routes import router as ocr_router   # bill scanning: GPU host first, CPU fallback (see ocr_routes.py)
app.include_router(ocr_router)
from . import label_routes
from .label_routes import router as label_router   # AC energy-label scanning (results only, nothing stored)
app.include_router(label_router)


async def _owned_bill(request: Request, bill_id: str, user: dict) -> tuple[dict, dict]:
    db: D.Db = request.app.state.db
    bill = await db.one(D.T_BILLS, bill_id=bill_id)
    household = await db.one(D.T_HOUSEHOLDS, household_id=bill["household_id"]) if bill else None
    if not bill or not household or household["user_id"] != user["id"]:
        raise HTTPException(404, "Bill not found")      # same answer for "not yours": no existence leak
    return bill, household


async def _baselines(request: Request) -> list[dict]:
    if request.app.state.baselines is None:                       # 130 rows; load once per process
        request.app.state.baselines = await request.app.state.db.many(D.T_BASELINES)
    return request.app.state.baselines


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/llm")
async def health_llm(request: Request):
    llm = request.app.state.llm
    out = {"mode": request.app.state.settings.engine_mode, "llm_base_url_set": bool(llm.base_url),
           "llm_reachable": await llm.ping()}
    info = await llm.info() if hasattr(llm, "info") else None
    if info:                                                   # gpu_service mode: compare hand-off files
        engine = request.app.state.jobs.engine
        out["model"] = info.get("model")
        out["catalog_matches_backend"] = info.get("catalog_sha256") == engine.catalog_sha256
    return out


@app.post("/bills/{bill_id}/analyze", status_code=202)
async def analyze(bill_id: str, request: Request, user: dict = Depends(current_user)):
    """Validate the bill, run the rule engine now (fast, CPU), queue advice generation (slow, GPU).
    Also used after the user edits a bill."""
    bill, household = await _owned_bill(request, bill_id, user)
    db: D.Db = request.app.state.db

    try:
        current = bills.normalize_bill(bill)
    except bills.BillDataError as e:
        raise HTTPException(422, {"code": "bill_invalid", "message": str(e)})
    problem = bills.tariff_problem(current["kwh"], current["price_sar"])
    if problem:
        raise HTTPException(422, {"code": "bill_inconsistent", "message": problem})

    rows = await db.many(D.T_BILLS, order="createdAt.desc", limit=40, household_id=household["household_id"])
    try:
        analysis = rule_engine.analyze_bill(bill=current, household=household,
                                            history=bills.recent_history(rows), baselines=await _baselines(request))
    except NotImplementedError as e:
        raise HTTPException(501, str(e))

    # Mirror the headline numbers into Bill (respecting its CHECK constraints) for the existing UI.
    values = {}
    if (analysis.get("similar_homes_kwh") or 0) > 0:
        values["regionAverageKwh"] = analysis["similar_homes_kwh"]
    if analysis.get("comparison_percentage") is not None:
        values["comparisonPercentage"] = analysis["comparison_percentage"]
    if (analysis.get("saving_kwh") or 0) >= 0 and analysis.get("saving_kwh") is not None:
        values["potentialSavingKwh"] = analysis["saving_kwh"]
    if values:
        await db.update(D.T_BILLS, values, bill_id=bill_id)

    # Re-analysis of an edited bill: if the user already applied some of its advice, keep that advice
    # (and their progress) and only refresh the numbers; otherwise generate advice for the new values.
    if any(r["isApplied"] for r in await db.many(D.T_ADVICE, bill_id=bill_id)):
        await db.update(D.T_JOBS, {"analysis": analysis}, bill_id=bill_id)
        return {"bill_id": bill_id, "analysis": analysis, "advice_status": "kept"}
    await request.app.state.jobs.enqueue(bill_id, analysis)
    return {"bill_id": bill_id, "analysis": analysis, "advice_status": "pending"}


@app.get("/bills/{bill_id}/advice")
async def get_advice(bill_id: str, request: Request, user: dict = Depends(current_user)):
    await _owned_bill(request, bill_id, user)
    db: D.Db = request.app.state.db
    job = await db.one(D.T_JOBS, bill_id=bill_id)
    rows = await db.many(D.T_ADVICE, bill_id=bill_id) if job and job["status"] == "done" else []
    return {
        "status": job["status"] if job else "none",
        "error": job["error"] if job else None,
        "advice": [{"id": r["adviceID"], "catalog_id": r.get("catalog_advice_id"), "title": r["adviceTitle"],
                    "category": r["adviceCategory"], "text": r["processedAdvice"],
                    "is_applied": r["isApplied"]} for r in rows],
    }


@app.post("/bills/{bill_id}/advice/regenerate", status_code=202)
async def regenerate(bill_id: str, request: Request, user: dict = Depends(current_user)):
    await _owned_bill(request, bill_id, user)
    db: D.Db = request.app.state.db
    job = await db.one(D.T_JOBS, bill_id=bill_id)
    if not job or not job.get("analysis"):
        raise HTTPException(409, "Run /analyze first")
    if any(r["isApplied"] for r in await db.many(D.T_ADVICE, bill_id=bill_id)):
        raise HTTPException(409, "Some advice is already marked as applied; regenerating would erase that progress")
    await request.app.state.jobs.enqueue(bill_id)
    return {"advice_status": "pending"}


class EndpointBody(BaseModel):
    url: str


@app.put("/admin/llm-endpoint")
async def set_llm_endpoint(body: EndpointBody, request: Request, x_admin_token: str = Header(...)):
    """Called by the GPU notebook (or you) whenever the tunnel URL changes."""
    if not hmac.compare_digest(x_admin_token, request.app.state.settings.admin_token):
        raise HTTPException(403, "Forbidden")
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(422, "url must start with http:// or https://")
    llm = request.app.state.llm
    llm.set_base_url(body.url)
    return {"llm_base_url": llm.base_url, "llm_reachable": await llm.ping()}
