from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _need(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass
class Settings:
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str      # server-side only. Bypasses RLS, so ownership is checked in code.
    engine_mode: str               # "gpu_service" (the original engine, recommended) | "openai" (vLLM, optional)
    llm_base_url: str              # GPU host URL. May be changed at runtime via PUT /admin/llm-endpoint.
    llm_api_key: str               # must equal GPU_API_KEY on the GPU service (or vllm --api-key)
    llm_model: str                 # only used in "openai" mode
    llm_timeout_s: float
    llm_concurrency: int           # only used in "openai" mode; gpu_service mode is always serial
    admin_token: str
    cors_origins: list[str]
    data_dir: Path


def load_settings() -> Settings:
    return Settings(
        supabase_url=_need("SUPABASE_URL").rstrip("/"),
        supabase_anon_key=_need("SUPABASE_ANON_KEY"),
        supabase_service_key=_need("SUPABASE_SERVICE_KEY"),
        engine_mode=os.getenv("ENGINE_MODE", "gpu_service").strip(),
        llm_base_url=os.getenv("LLM_BASE_URL", "").rstrip("/"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "Qwen/Qwen3-4B-Instruct-2507"),
        llm_timeout_s=float(os.getenv("LLM_TIMEOUT_S", "300")),
        llm_concurrency=int(os.getenv("LLM_CONCURRENCY", "2")),
        admin_token=_need("ADMIN_TOKEN"),
        cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()],
        data_dir=Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent.parent / "data")),
    )
