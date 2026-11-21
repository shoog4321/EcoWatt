"""Backend-side engine for ENGINE_MODE=gpu_service.

The GPU service runs the original AdviceEngine unchanged (generation + its own safety layer). This class adds the
checks that engine does not do, WITHOUT touching model behaviour:
  * drop ids not in the approved catalog, winter-only items on non-winter bills, excluded ids, duplicates, over-long text, text containing the user's name
  * require 3..6 valid items (the engine's schema enforces the count, but duplicates can still slip through)
  * verify the GPU host runs the same catalog file as this backend (a changed catalog invalidates the evaluation)
  * the advice text never includes the user's name (names are only used to drop items that leak them)
Dropping an item can only remove content, never alter safety wording.
"""
from __future__ import annotations

import logging

from .advice_engine import (MAX_ITEMS, MIN_ITEMS, AdviceGenerationError, CatalogItem, GenerationResult,
                            check_items)
from .gpu_client import GpuClient

log = logging.getLogger("ecowatt.remote")


class RemoteAdviceEngine:
    def __init__(self, gpu: GpuClient, catalog: dict[str, CatalogItem], catalog_sha256: str):
        self.llm = gpu                  # attribute name used by jobs.py / main.py
        self.catalog, self.catalog_sha256 = catalog, catalog_sha256

    async def generate(self, *, case_id: str, profile: dict, period: dict, analysis: dict,
                       first_name: str = "", last_name: str = "",
                       exclude_ids: frozenset[str] = frozenset()) -> GenerationResult:
        data = await self.llm.generate(profile, period, analysis, exclude_ids=sorted(exclude_ids))

        remote_sha = data.get("catalog_sha256")
        if remote_sha and remote_sha != self.catalog_sha256:
            raise AdviceGenerationError(
                "GPU service uses a different advice_catalog.json than this backend "
                f"(gpu {remote_sha[:12]}… vs backend {self.catalog_sha256[:12]}…). "
                "Deploy the same hand-off files on both sides.")

        raw = [{"advice_id": str(a.get("advice_id")), "personalized_advice": str(a.get("personalized_advice", "")).strip()}
               for a in data.get("advice", []) if isinstance(a, dict)]
        names = [n for n in (first_name, last_name) if n and len(n) > 1]
        items, errors = check_items(raw, self.catalog, names, season=period.get("season") or "",
                                    exclude=frozenset(exclude_ids))
        for e in errors:
            log.warning("dropped item for %s: %s", case_id, e)
        if len(items) < MIN_ITEMS:
            raise AdviceGenerationError(f"Only {len(items)} valid advice items after validation ({case_id}): {errors}")
        items = items[:MAX_ITEMS]

        safe = {a.get("advice_id"): bool(a.get("safe")) for a in data.get("audit", []) if isinstance(a, dict)}
        audit = [{"advice_id": it["advice_id"], "safety": "ok" if safe.get(it["advice_id"], False) else "unresolved"}
                 for it in items]
        audit += [{"dropped": e} for e in errors]
        for a in audit:
            if a.get("safety") == "unresolved":
                log.warning("safety condition not confirmed for %s", a["advice_id"])

        enriched = [{**it, "title": self.catalog[it["advice_id"]].title, "type": self.catalog[it["advice_id"]].type}
                    for it in items]
        return GenerationResult(enriched, audit)
