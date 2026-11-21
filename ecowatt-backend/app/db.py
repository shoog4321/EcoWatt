"""Supabase access through PostgREST with the service-role key.

Table names match your real schema (quoted, capitalised). Column names are used literally
in the code (bill_id, household_id, firstName, ...) because the schema is now known.
"""
from __future__ import annotations

import httpx

from .config import Settings

T_USERS, T_HOUSEHOLDS, T_BILLS, T_USAGE, T_ADVICE = "User", "Household", "Bill", "Usage", "Advice"
T_BASELINES = "consumption_baselines"
T_JOBS = "advice_jobs"          # created by sql/001_advice_jobs.sql (backend-write-only)


class Db:
    def __init__(self, http: httpx.AsyncClient, s: Settings):
        self.http = http
        self.base = f"{s.supabase_url}/rest/v1"
        self.h = {"apikey": s.supabase_service_key, "Authorization": f"Bearer {s.supabase_service_key}",
                  "Content-Type": "application/json"}

    async def _call(self, method: str, table: str, params: dict | None = None, json=None, prefer: str | None = None):
        headers = dict(self.h)
        if prefer:
            headers["Prefer"] = prefer
        r = await self.http.request(method, f"{self.base}/{table}", params=params, json=json,
                                    headers=headers, timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"Supabase {method} {table} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    async def one(self, table: str, **eq) -> dict | None:
        rows = await self._call("GET", table, {"select": "*", "limit": 1, **{k: f"eq.{v}" for k, v in eq.items()}})
        return rows[0] if rows else None

    async def many(self, table: str, order: str | None = None, limit: int | None = None, **eq) -> list[dict]:
        params = {"select": "*", **{k: f"eq.{v}" for k, v in eq.items()}}
        if order:
            params["order"] = order
        if limit:
            params["limit"] = limit
        return await self._call("GET", table, params) or []

    async def update(self, table: str, values: dict, **eq) -> None:
        await self._call("PATCH", table, {k: f"eq.{v}" for k, v in eq.items()}, json=values)

    async def update_where(self, table: str, values: dict, filters: dict[str, str]) -> None:
        await self._call("PATCH", table, filters, json=values)

    async def upsert(self, table: str, row: dict, on_conflict: str) -> None:
        await self._call("POST", table, {"on_conflict": on_conflict}, json=row,
                         prefer="resolution=merge-duplicates")

    async def delete(self, table: str, **eq) -> None:
        await self._call("DELETE", table, {k: f"eq.{v}" for k, v in eq.items()})

    async def insert(self, table: str, rows: list[dict]) -> None:
        await self._call("POST", table, json=rows)
