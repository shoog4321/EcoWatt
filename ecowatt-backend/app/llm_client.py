"""Thin client for the GPU inference server (vLLM, OpenAI-compatible API).

The backend only ever knows `LLM_BASE_URL`, so moving from Kaggle+ngrok to any
other GPU host is a one-variable change (or a call to PUT /admin/llm-endpoint).
"""
from __future__ import annotations

import asyncio

import httpx

from .config import Settings


class LLMUnavailable(RuntimeError):
    """GPU endpoint is down / unreachable. Retry later; this is not a content failure."""


class LLMClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings):
        self.http, self.s = http, settings
        self._sem = asyncio.Semaphore(settings.llm_concurrency)

    def set_base_url(self, url: str) -> None:
        self.s.llm_base_url = url.rstrip("/")

    @property
    def base_url(self) -> str:
        return self.s.llm_base_url

    def _headers(self) -> dict:
        h = {"ngrok-skip-browser-warning": "true"}
        if self.s.llm_api_key:
            h["Authorization"] = f"Bearer {self.s.llm_api_key}"
        return h

    async def complete_json(self, messages: list[dict], schema: dict, max_tokens: int = 640) -> str:
        if not self.base_url:
            raise LLMUnavailable("LLM endpoint is not configured (set LLM_BASE_URL or PUT /admin/llm-endpoint).")
        payload = {
            "model": self.s.llm_model,
            "messages": messages,
            "temperature": 0,               # greedy, as in the evaluation
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "advice", "schema": schema, "strict": True},
            },
        }
        last: object = None
        for attempt in range(3):
            try:
                async with self._sem:
                    r = await self.http.post(
                        f"{self.base_url}/v1/chat/completions", json=payload,
                        headers=self._headers(), timeout=self.s.llm_timeout_s,
                    )
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
                last = e
            else:
                if r.status_code == 200:
                    try:
                        return r.json()["choices"][0]["message"]["content"]
                    except (KeyError, IndexError, ValueError) as e:
                        raise LLMUnavailable(f"Unexpected LLM response shape: {r.text[:200]}") from e
                if r.status_code >= 500 or r.status_code == 404:   # tunnel down / server restarting
                    last = f"HTTP {r.status_code}"
                else:                                               # 400/401/422: our request is wrong
                    raise LLMUnavailable(f"LLM rejected the request: HTTP {r.status_code} {r.text[:300]}")
            await asyncio.sleep(2 ** attempt)
        raise LLMUnavailable(f"LLM endpoint unreachable after 3 attempts: {last!r}")

    async def ping(self) -> bool:
        if not self.base_url:
            return False
        try:
            r = await self.http.get(f"{self.base_url}/health", headers=self._headers(), timeout=10)
            return r.status_code == 200
        except httpx.HTTPError:
            return False
