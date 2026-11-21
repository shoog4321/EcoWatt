"""Background advice generation with GPU-outage tolerance.

State lives in advice_jobs (backend-write-only):  pending -> running -> done | failed
GPU endpoint down  -> back to `pending`; the sweeper retries every minute.
Content failure    -> `failed` (retry via POST /bills/{id}/advice/regenerate).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from . import bills as B
from . import db as D
from .advice_engine import AdviceEngine, excluded_ids
from .llm_client import LLMUnavailable
from .profiles import build_profile

log = logging.getLogger("ecowatt.jobs")

# Enum advice_category_enum in your database
CATEGORIES = {"cooling", "lighting", "electronics", "behavior", "insulation", "refrigeration",
              "water heating", "laundry", "cooking"}
# Hand-off catalog types that are not enum values -> closest enum value
CATEGORY_ALIASES = {"heating": "behavior",        # ADV_001-003 heating thermostat / occupied rooms (winter)
                    "appliances": "laundry"}      # ADV_056 clothes dryer full loads
# The analysis keys the model was evaluated on (notebook section 3.1). Backend-only fields such as
# saving_kwh are stored on the Bill but not shown to the model.
LLM_ANALYSIS_KEYS = ("month", "year", "season", "consumption_level", "comparison_percentage", "drivers",
                     "message", "actual_kwh", "similar_homes_kwh", "saving_sar", "comparison_available")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class AdviceJobs:
    def __init__(self, db: D.Db, engine: AdviceEngine):
        self.db, self.engine = db, engine
        self.inflight: set[str] = set()
        self._tasks: set[asyncio.Task] = set()

    async def enqueue(self, bill_id: str, analysis: dict | None = None) -> None:
        row = {"bill_id": bill_id, "status": "pending", "error": None, "audit": None, "updated_at": _now()}
        if analysis is not None:
            row["analysis"] = analysis
        await self.db.upsert(D.T_JOBS, row, on_conflict="bill_id")
        self.schedule(bill_id)

    def schedule(self, bill_id: str) -> None:
        task = asyncio.create_task(self.run(bill_id))
        self._tasks.add(task)                       # hold a reference so it isn't garbage-collected
        task.add_done_callback(self._tasks.discard)

    async def run(self, bill_id: str) -> None:
        if bill_id in self.inflight:
            return
        self.inflight.add(bill_id)
        try:
            await self._run(bill_id)
        finally:
            self.inflight.discard(bill_id)

    async def _run(self, bill_id: str) -> None:
        db = self.db
        try:
            job = await db.one(D.T_JOBS, bill_id=bill_id)
            if not job or job["status"] != "pending" or not job.get("analysis"):
                return
            await self._set(bill_id, "running", None)

            bill = await db.one(D.T_BILLS, bill_id=bill_id)
            household = await db.one(D.T_HOUSEHOLDS, household_id=bill["household_id"])
            usage = (await db.many(D.T_USAGE, order="last_updated.desc", limit=1,
                                   household_id=household["household_id"]) or [None])[0]
            user = await db.one(D.T_USERS, id=household["user_id"]) or {}
            analysis = job["analysis"]
            profile = build_profile(household, usage)
            dropped, usage_note = await self._usage_dropped(household["household_id"], bill_id)
            # Applied tips are skipped only when they seem to have worked (usage went down);
            # otherwise repeating them is better than falling back to unrelated advice.
            applied = await self._applied_ids(household["household_id"]) if dropped else set()
            exclude = excluded_ids(self.engine.catalog, season=analysis.get("season"),
                                   willing_to_upgrade=profile.get("willingToUpgradeAppliance"),
                                   applied=applied)

            result = await self.engine.generate(
                case_id=f"{household['household_id']}_{analysis['year']}_{analysis['month']}",
                profile=profile,
                period={"month": analysis["month"], "year": analysis["year"], "season": analysis["season"]},
                analysis={k: analysis[k] for k in LLM_ANALYSIS_KEYS if k in analysis},
                first_name=user.get("firstName", ""),
                last_name=user.get("lastName", ""),
                exclude_ids=exclude,
            )

            rows = []
            for it in result.items:
                category = it["type"].strip().lower()
                category = CATEGORY_ALIASES.get(category, category)
                if category not in CATEGORIES:
                    raise ValueError(f"Catalog type {it['type']!r} ({it['advice_id']}) is not in advice_category_enum")
                rows.append({
                    "bill_id": bill_id,
                    "processedAdvice": it["personalized_advice"],
                    "adviceCategory": category,
                    "adviceTitle": (it["title"] or f"{category.capitalize()} advice")[:120],
                    "isApplied": False,
                    "catalog_advice_id": it["advice_id"],
                })
            await db.delete(D.T_ADVICE, bill_id=bill_id)
            await db.insert(D.T_ADVICE, rows)
            await self._set(bill_id, "done", None, audit=result.audit + [{"applied_tips": usage_note}])
            log.info("advice ready for bill %s (%d items)", bill_id, len(rows))

        except LLMUnavailable as e:
            log.warning("GPU unavailable for bill %s: %s", bill_id, e)
            await self._set(bill_id, "pending", str(e))
        except Exception as e:                      # content/data errors: do not retry forever
            log.exception("advice generation failed for bill %s", bill_id)
            await self._set(bill_id, "failed", f"{type(e).__name__}: {e}")

    async def _usage_dropped(self, household_id: str, bill_id: str) -> tuple[bool, str]:
        """Did this bill's consumption go down compared with the household's previous valid bill?
        No previous bill -> treated as dropped (nothing suggests the applied tips failed)."""
        rows = await self.db.many(D.T_BILLS, order="createdAt.desc", household_id=household_id)
        history = B.recent_history(rows, n=len(rows) or 1)                     # newest period first
        current = next((b for b in history if b["bill_id"] == bill_id), None)
        if current is None:
            return True, "excluded (bill not comparable)"
        previous = next((b for b in history if (b["year"], b["month"]) < (current["year"], current["month"])), None)
        if previous is None:
            return True, "excluded (no previous bill)"
        change = f"{previous['kwh']:g} -> {current['kwh']:g} kWh"
        if current["kwh"] < previous["kwh"]:
            return True, f"excluded (usage dropped {change})"
        return False, f"may repeat (usage did not drop {change})"

    async def _applied_ids(self, household_id: str) -> set[str]:
        """Catalog ids the household already marked as applied, on any of its bills."""
        applied: set[str] = set()
        for bill in await self.db.many(D.T_BILLS, household_id=household_id):
            for row in await self.db.many(D.T_ADVICE, bill_id=bill["bill_id"]):
                if row.get("isApplied") and row.get("catalog_advice_id"):
                    applied.add(row["catalog_advice_id"])
        return applied

    async def _set(self, bill_id: str, status: str, error: str | None, **extra) -> None:
        try:
            await self.db.update(D.T_JOBS, {"status": status, "error": error[:500] if error else None,
                                            "updated_at": _now(), **extra}, bill_id=bill_id)
        except Exception:
            log.exception("could not record status for bill %s", bill_id)

    async def sweeper(self, interval_s: int = 60) -> None:
        """Re-queue jobs waiting for the GPU; also recovers jobs interrupted by a restart."""
        try:
            await self.db.update_where(D.T_JOBS, {"status": "pending"}, {"status": "eq.running"})
        except Exception:
            log.exception("startup reset of 'running' jobs failed")
        while True:
            await asyncio.sleep(interval_s)
            try:
                if self.engine.llm.base_url:
                    for job in await self.db.many(D.T_JOBS, limit=5, status="pending"):
                        if job["bill_id"] not in self.inflight:
                            self.schedule(job["bill_id"])
            except Exception:
                log.exception("sweeper iteration failed")
