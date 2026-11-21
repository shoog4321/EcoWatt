"""Analyse bills that were saved before the backend was connected (the app only analyses newly added bills).

For every household:
  * each valid, not-yet-analysed bill gets the rule-engine numbers written to its Bill row (home-screen trend/compare)
  * the household's newest valid bill gets an advice job queued if it has none; the running backend's sweeper
    generates it within a minute while the GPU is up
Bills that fail the tariff check are skipped, exactly as POST /bills/{id}/analyze would reject them.

Run from the project root:  .venv/bin/python -m scripts.analyze_existing_bills [--dry-run]
"""
from __future__ import annotations

import asyncio
import datetime as dt
import sys

import httpx
from dotenv import load_dotenv

load_dotenv(".env")

from app import bills, rule_engine  # noqa: E402
from app import db as D  # noqa: E402
from app.config import load_settings  # noqa: E402


def _bill_values(analysis: dict) -> dict:
    """Same mapping (and CHECK-constraint guards) as POST /bills/{id}/analyze."""
    values = {}
    if (analysis.get("similar_homes_kwh") or 0) > 0:
        values["regionAverageKwh"] = analysis["similar_homes_kwh"]
    if analysis.get("comparison_percentage") is not None:
        values["comparisonPercentage"] = analysis["comparison_percentage"]
    if analysis.get("saving_kwh") is not None and analysis["saving_kwh"] >= 0:
        values["potentialSavingKwh"] = analysis["saving_kwh"]
    return values


async def main(dry_run: bool) -> None:
    s = load_settings()
    async with httpx.AsyncClient() as http:
        db = D.Db(http, s)
        baselines = await db.many(D.T_BASELINES)
        jobs = {j["bill_id"] for j in await db.many(D.T_JOBS)}
        analysed = queued = 0

        for household in await db.many(D.T_HOUSEHOLDS):
            rows = await db.many(D.T_BILLS, order="createdAt.desc", household_id=household["household_id"])
            history = bills.recent_history(rows, n=len(rows) or 1)           # valid, one per period, newest first
            if not history:
                continue
            by_id = {r["bill_id"]: r for r in rows}
            for i, bill in enumerate(history):
                row = by_id[bill["bill_id"]]
                newest = i == 0
                needs_numbers = row.get("regionAverageKwh") is None and bill["bill_id"] not in jobs
                needs_advice = newest and bill["bill_id"] not in jobs
                if not (needs_numbers or needs_advice):
                    continue
                analysis = rule_engine.analyze_bill(bill=bill, household=household,
                                                    history=history[i + 1:i + 7], baselines=baselines)
                label = f"{household['region']} {household['housingType']}: {bill['year']}-{bill['month']:02d}"
                print(f"{'[dry run] ' if dry_run else ''}{label}  {analysis['consumption_level']}, "
                      f"similar={analysis['similar_homes_kwh']}, saving={analysis['saving_sar']} SAR"
                      f"{'  + advice job' if needs_advice else ''}")
                if dry_run:
                    continue
                values = _bill_values(analysis)
                if values:
                    await db.update(D.T_BILLS, values, bill_id=bill["bill_id"])
                analysed += 1
                if needs_advice:
                    await db.upsert(D.T_JOBS, {"bill_id": bill["bill_id"], "status": "pending", "error": None,
                                               "audit": None, "analysis": analysis,
                                               "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                                    on_conflict="bill_id")
                    queued += 1
        print(f"analysed {analysed} bills, queued {queued} advice jobs")


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
