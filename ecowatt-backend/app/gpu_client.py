"""Client for gpu_service (the original AdviceEngine behind HTTP).

Same surface as LLMClient (base_url / set_base_url / ping) so jobs.py and the admin endpoint work with either.
"""
from __future__ import annotations

import asyncio

import httpx

from .advice_engine import AdviceGenerationError
from .config import Settings
from .llm_client import LLMUnavailable


class GpuClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings):
        self.http, self.s = http, settings
        self._sem = asyncio.Semaphore(1)        # the GPU does one generation at a time; do not queue timeouts

    @property
    def base_url(self) -> str:
        return self.s.llm_base_url

    def set_base_url(self, url: str) -> None:
        self.s.llm_base_url = url.rstrip("/")

    def _headers(self) -> dict:
        h = {"ngrok-skip-browser-warning": "true"}
        if self.s.llm_api_key:
            h["Authorization"] = f"Bearer {self.s.llm_api_key}"
        return h

    async def info(self) -> dict | None:
        if not self.base_url:
            return None
        try:
            r = await self.http.get(f"{self.base_url}/health", headers=self._headers(), timeout=10)
            return r.json() if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None

    async def ping(self) -> bool:
        return await self.info() is not None

    async def generate(self, profile: dict, period: dict, analysis: dict,
                       exclude_ids: list[str] | None = None) -> dict:
        if not self.base_url:
            raise LLMUnavailable("GPU endpoint is not configured (set LLM_BASE_URL or PUT /admin/llm-endpoint).")
        body = {"profile": profile, "period": period, "analysis": analysis, "exclude_ids": exclude_ids or []}
        last: object = None
        for attempt in range(3):
            try:
                async with self._sem:
                    r = await self.http.post(f"{self.base_url}/generate", json=body,
                                             headers=self._headers(), timeout=self.s.llm_timeout_s)
            except httpx.ReadTimeout as e:
                # The GPU may still be generating: retrying now would queue a duplicate behind it.
                raise LLMUnavailable("GPU service timed out while generating; will retry later.") from e
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
                last = e                                   # tunnel down / host restarting
            else:
                if r.status_code == 200:
                    try:
                        return r.json()
                    except ValueError as e:
                        raise LLMUnavailable(f"GPU service returned non-JSON: {r.text[:200]}") from e
                payload = _json_or_empty(r)
                if r.status_code == 422 and payload.get("error") == "model_invalid_output":
                    raise AdviceGenerationError(f"Model produced unusable output: {payload.get('detail', '')[:300]}")
                if r.status_code in (401, 403):
                    raise LLMUnavailable("GPU service rejected the API key (LLM_API_KEY must equal GPU_API_KEY).")
                if r.status_code >= 500 or r.status_code in (404, 429):    # 404 = ngrok tunnel offline
                    last = f"HTTP {r.status_code}"
                else:
                    raise LLMUnavailable(f"GPU service rejected the request: HTTP {r.status_code} {r.text[:300]}")
            await asyncio.sleep(2 ** attempt)
        raise LLMUnavailable(f"GPU service unreachable after 3 attempts: {last!r}")

    async def ocr(self, data: bytes, filename: str) -> dict | None:
        """Scan a bill on the GPU host. None when the GPU is unreachable or has no OCR (caller falls back)."""
        if not self.base_url:
            return None
        try:
            r = await self.http.post(f"{self.base_url}/ocr", files={"file": (filename, data)},
                                     headers=self._headers(), timeout=90)
        except httpx.HTTPError:
            return None
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                return None
        if r.status_code in (400, 413):          # the image itself is the problem: report it, do not fall back
            raise ValueError(_json_or_empty(r).get("detail") or "Please upload a valid JPG or PNG image.")
        return None                               # 404 (old GPU service / tunnel down), 401, 5xx -> fall back


def _json_or_empty(r) -> dict:
    try:
        data = r.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}
