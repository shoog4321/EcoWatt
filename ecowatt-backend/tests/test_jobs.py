"""Job state machine against an in-memory DB. Stubs httpx so it runs without installs.
Run:  python -m tests.test_jobs"""
import asyncio
import types

from tests import _httpx_stub  # noqa: F401

from app import db as D
from app.advice_engine import AdviceGenerationError, CatalogItem, GenerationResult
from app.jobs import AdviceJobs
from app.llm_client import LLMUnavailable

ANALYSIS = {"month": 10, "year": 2026, "season": "rest_of_year"}


class FakeDb:
    def __init__(self, job_status="pending"):
        self.t = {
            D.T_BILLS: [{"bill_id": "b1", "household_id": "h1"}],
            D.T_HOUSEHOLDS: [{"household_id": "h1", "user_id": "u1", "region": "Riyadh", "homeSize": "225"}],
            D.T_USAGE: [{"household_id": "h1", "last_updated": "2", "applies_energy_tips": True},
                        {"household_id": "h1", "last_updated": "1", "applies_energy_tips": False}],
            D.T_ADVICE: [],
            D.T_USERS: [{"id": "u1", "firstName": "Sara", "lastName": "Alharbi"}],
            D.T_JOBS: [{"bill_id": "b1", "status": job_status, "analysis": ANALYSIS}],
        }

    def _m(self, r, eq):
        return all(str(r.get(k)) == str(v) for k, v in eq.items())

    async def one(self, table, **eq):
        return next((r for r in self.t[table] if self._m(r, eq)), None)

    async def many(self, table, order=None, limit=None, **eq):
        rows = [r for r in self.t[table] if self._m(r, eq)]
        return rows[:limit] if limit else rows

    async def update(self, table, values, **eq):
        for r in self.t[table]:
            if self._m(r, eq):
                r.update(values)

    async def delete(self, table, **eq):
        self.t[table] = [r for r in self.t[table] if not self._m(r, eq)]

    async def insert(self, table, rows):
        self.t[table].extend(rows)

    async def upsert(self, table, row, on_conflict):
        existing = await self.one(table, **{on_conflict: row[on_conflict]})
        existing.update(row) if existing else self.t[table].append(dict(row))


class Engine:
    def __init__(self, outcome):
        self.outcome, self.llm, self.seen = outcome, types.SimpleNamespace(base_url="x"), None
        self.catalog = {a: CatalogItem(a, "cooling", "", "x", "all", a == "ADV_054")
                        for a in ("ADV_001", "ADV_004", "ADV_054")}

    async def generate(self, **kw):
        self.seen = kw
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def item(aid="ADV_001", type_="Cooling", title="AC"):
    return {"advice_id": aid, "personalized_advice": "Sara, set the AC to 24.", "title": title, "type": type_}


GOOD = GenerationResult([item()], [{"advice_id": "ADV_001", "safety": "ok"}])


def run(outcome, job_status="pending"):
    db, eng = FakeDb(job_status), Engine(outcome)
    asyncio.run(AdviceJobs(db, eng).run("b1"))
    return db, eng


def test_success_uses_latest_usage_and_hides_identity():
    db, eng = run(GOOD)
    job = db.t[D.T_JOBS][0]
    assert job["status"] == "done" and job["audit"][0]["safety"] == "ok"
    row = db.t[D.T_ADVICE][0]
    assert row["catalog_advice_id"] == "ADV_001" and row["adviceCategory"] == "cooling"
    assert eng.seen["profile"]["appliesEnergyTips"] == "Yes"        # newest Usage row (last_updated=2)
    assert "user_id" not in eng.seen["profile"] and eng.seen["first_name"] == "Sara"


def test_gpu_down_returns_to_pending_for_retry():
    db, _ = run(LLMUnavailable("tunnel offline"))
    job = db.t[D.T_JOBS][0]
    assert job["status"] == "pending" and "tunnel offline" in job["error"] and db.t[D.T_ADVICE] == []


def test_content_failure_is_failed_not_retried():
    assert run(AdviceGenerationError("only 1 valid item"))[0].t[D.T_JOBS][0]["status"] == "failed"


def test_category_outside_enum_fails_loudly():
    db, _ = run(GenerationResult([item(type_="Gardening")], []))
    job = db.t[D.T_JOBS][0]
    assert job["status"] == "failed" and "advice_category_enum" in job["error"] and db.t[D.T_ADVICE] == []


def test_empty_title_gets_a_fallback():
    db, _ = run(GenerationResult([item(title="")], []))
    assert db.t[D.T_ADVICE][0]["adviceTitle"] == "Cooling advice"


def test_non_pending_job_is_ignored():
    db, _ = run(GOOD, job_status="done")
    assert db.t[D.T_ADVICE] == []


def test_applied_and_declined_purchase_tips_are_excluded():
    db, eng = FakeDb(), Engine(GOOD)
    db.t[D.T_BILLS].append({"bill_id": "b0", "household_id": "h1"})
    db.t[D.T_ADVICE].append({"bill_id": "b0", "catalog_advice_id": "ADV_004", "isApplied": True})
    db.t[D.T_ADVICE].append({"bill_id": "b0", "catalog_advice_id": "ADV_001", "isApplied": False})
    db.t[D.T_USAGE][0]["willing_to_upgrade_appliance"] = False
    asyncio.run(AdviceJobs(db, eng).run("b1"))
    # tiny 3-item test catalog: applied ADV_004 would leave too few items, so only the purchase is excluded
    assert eng.seen["exclude_ids"] == {"ADV_054"}


def _usage_case(prev_kwh, cur_kwh):
    def price(k):                                    # tariff-consistent price
        return round(k * 0.18 * 1.15 + 15, 2)
    db, eng = FakeDb(), Engine(GOOD)
    eng.catalog = {f"ADV_{n:03d}": CatalogItem(f"ADV_{n:03d}", "cooling", "", "x") for n in range(1, 13)}
    db.t[D.T_BILLS] = [
        {"bill_id": "b1", "household_id": "h1", "month": "October", "year": "2026",
         "consumption": cur_kwh, "price": price(cur_kwh), "createdAt": "2"},
        {"bill_id": "b0", "household_id": "h1", "month": "September", "year": "2026",
         "consumption": prev_kwh, "price": price(prev_kwh), "createdAt": "1"},
    ]
    db.t[D.T_ADVICE].append({"bill_id": "b0", "catalog_advice_id": "ADV_004", "isApplied": True})
    asyncio.run(AdviceJobs(db, eng).run("b1"))
    return db, eng


def test_applied_tips_skipped_when_usage_dropped():
    db, eng = _usage_case(600, 500)
    assert eng.seen["exclude_ids"] == {"ADV_004"}
    assert "dropped" in db.t[D.T_JOBS][0]["audit"][-1]["applied_tips"]


def test_applied_tips_may_repeat_when_usage_did_not_drop():
    db, eng = _usage_case(500, 600)
    assert eng.seen["exclude_ids"] == frozenset()
    assert "may repeat" in db.t[D.T_JOBS][0]["audit"][-1]["applied_tips"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
