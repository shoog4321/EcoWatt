"""HTTP-level tests of the logged-in API paths (FastAPI TestClient, in-memory database, no network).
Run with the backend's virtualenv:  .venv/bin/python -m tests.test_api
"""
import asyncio

try:
    from fastapi.testclient import TestClient
except ImportError:                                  # system Python without the backend packages
    TestClient = None

from tests.test_rule_engine import BASELINES

ME, OTHER = "user-me", "user-other"


class FakeDb:
    """Just enough of app.db.Db for main.py."""

    def __init__(self):
        from app import db as D
        self.D = D
        self.t = {
            D.T_HOUSEHOLDS: [
                {"household_id": "h-me", "user_id": ME, "region": "Riyadh", "housingType": "Villa",
                 "acType": "Window", "hasInsulation": False, "numberOfResidents": 7, "homeSize": "225"},
                {"household_id": "h-other", "user_id": OTHER, "region": "Riyadh", "housingType": "Villa"},
            ],
            D.T_BILLS: [
                {"bill_id": "b-ok", "household_id": "h-me", "month": "July", "year": "2026",
                 "consumption": 9800, "price": 2600, "createdAt": "2"},
                {"bill_id": "b-typo", "household_id": "h-me", "month": "June", "year": "2026",
                 "consumption": 1580, "price": 600, "createdAt": "1"},
                {"bill_id": "b-other", "household_id": "h-other", "month": "July", "year": "2026",
                 "consumption": 9800, "price": 2600, "createdAt": "1"},
            ],
            D.T_ADVICE: [], D.T_JOBS: [], D.T_BASELINES: BASELINES,
        }
        self.updates = []

    def _m(self, r, eq):
        return all(str(r.get(k)) == str(v) for k, v in eq.items())

    async def one(self, table, **eq):
        return next((r for r in self.t[table] if self._m(r, eq)), None)

    async def many(self, table, order=None, limit=None, **eq):
        return [r for r in self.t[table] if self._m(r, eq)][:limit]

    async def update(self, table, values, **eq):
        self.updates.append((table, values, eq))
        for r in self.t[table]:
            if self._m(r, eq):
                r.update(values)


class FakeJobs:
    def __init__(self, db):
        self.db, self.enqueued = db, []

    async def enqueue(self, bill_id, analysis=None):
        self.enqueued.append(bill_id)
        rows = self.db.t[self.db.D.T_JOBS]
        row = next((r for r in rows if r["bill_id"] == bill_id), None)
        if row is None:
            rows.append({"bill_id": bill_id, "status": "pending", "analysis": analysis, "error": None})
        else:
            row.update(status="pending", **({"analysis": analysis} if analysis else {}))


def client():
    from app import main
    from app.auth import current_user
    db = FakeDb()
    jobs = FakeJobs(db)
    main.app.state.db, main.app.state.jobs, main.app.state.baselines = db, jobs, None
    main.app.dependency_overrides[current_user] = lambda: {"id": ME}
    return TestClient(main.app), db, jobs


def test_analyze_own_bill_runs_rule_engine_and_queues_advice():
    c, db, jobs = client()
    r = c.post("/bills/b-ok/analyze")
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["advice_status"] == "pending" and jobs.enqueued == ["b-ok"]
    a = body["analysis"]
    assert a["season"] == "rest_of_year" and a["consumption_level"] in {"High", "Moderate", "Average", "Low"}
    assert a["drivers"] == ["Poor insulation", "Low efficiency AC", "High occupancy"]
    bill = next(b for b in db.t[db.D.T_BILLS] if b["bill_id"] == "b-ok")
    assert bill["regionAverageKwh"] > 0 and bill["potentialSavingKwh"] >= 0      # mirrored for the home screen


def test_someone_elses_bill_is_not_found():
    c, _, jobs = client()
    assert c.post("/bills/b-other/analyze").status_code == 404
    assert c.get("/bills/b-other/advice").status_code == 404
    assert c.post("/bills/b-other/advice/regenerate").status_code == 404
    assert c.post("/bills/does-not-exist/analyze").status_code == 404
    assert jobs.enqueued == []


def test_typo_bill_is_rejected_with_a_readable_message():
    c, _, jobs = client()
    r = c.post("/bills/b-typo/analyze")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "bill_inconsistent"
    assert "should cost about" in r.json()["detail"]["message"] and jobs.enqueued == []


def test_edited_bill_keeps_applied_advice():
    c, db, jobs = client()
    db.t[db.D.T_JOBS].append({"bill_id": "b-ok", "status": "done", "analysis": {"month": 7}})
    db.t[db.D.T_ADVICE].append({"bill_id": "b-ok", "isApplied": True, "adviceID": "a1"})
    r = c.post("/bills/b-ok/analyze")
    assert r.status_code == 202 and r.json()["advice_status"] == "kept" and jobs.enqueued == []
    assert db.t[db.D.T_JOBS][0]["analysis"]["season"] == "rest_of_year"        # numbers refreshed
    assert db.t[db.D.T_JOBS][0]["status"] == "done"                              # advice left untouched


def test_advice_status_and_regenerate_rules():
    c, db, jobs = client()
    assert c.get("/bills/b-ok/advice").json()["status"] == "none"
    assert c.post("/bills/b-ok/advice/regenerate").status_code == 409            # analyze first
    c.post("/bills/b-ok/analyze")
    assert c.get("/bills/b-ok/advice").json()["status"] == "pending"
    db.t[db.D.T_ADVICE].append({"bill_id": "b-ok", "isApplied": True, "adviceID": "a1"})
    assert c.post("/bills/b-ok/advice/regenerate").status_code == 409            # would erase progress


def test_scan_rejects_non_images():
    c, _, _ = client()
    import types
    from app import main
    main.app.state.llm = types.SimpleNamespace()                                 # no GPU OCR available
    r = c.post("/analyze-bill", files={"file": ("x.txt", b"hello")})
    assert r.status_code == 400 and "JPG or PNG" in r.json()["detail"]


def test_ac_label_scan_rules():
    c, _, _ = client()
    from app import label_routes
    r = c.post("/analyze-ac-label", files={"file": ("x.txt", b"hello")})
    assert r.status_code == 400 and "energy label" in r.json()["detail"]
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    original_find, original_scan = label_routes.importlib.util.find_spec, label_routes._scan
    try:
        label_routes.importlib.util.find_spec = lambda name: None              # PaddleOCR not installed
        r = c.post("/analyze-ac-label", files={"file": ("l.png", png)})
        assert r.status_code == 503 and "not available" in r.json()["detail"]
        label_routes.importlib.util.find_spec = lambda name: object()
        label_routes._scan = lambda path: {"success": True, "grade": "D", "annual_kwh": 6049.0}
        r = c.post("/analyze-ac-label", files={"file": ("l.png", png)})
        assert r.status_code == 200 and r.json()["grade"] == "D"                 # result returned, nothing stored
    finally:
        label_routes.importlib.util.find_spec, label_routes._scan = original_find, original_scan


def test_label_grade_mapping_and_numbers():
    from app.label_ocr import ARABIC_TO_LATIN_GRADE, _number
    assert [ARABIC_TO_LATIN_GRADE[g] for g in ("أ", "ب", "ج", "د", "هـ", "و", "ز")] == list("ABCDEFG")
    assert _number("18,600") == 18600 and _number("5.46") == 5.46 and _number("") is None and _number("x") is None


def test_small_label_images_are_enlarged_before_scanning():
    import tempfile
    from pathlib import Path
    from PIL import Image
    from app.label_ocr import MIN_SCAN_SIDE, _enlarge_if_small
    d = Path(tempfile.mkdtemp())
    Image.new("RGB", (550, 550), "white").save(d / "small.png")
    Image.new("RGB", (1600, 1200), "white").save(d / "big.png")
    out = _enlarge_if_small(d / "small.png", d / "small_big.png")
    assert out.name == "small_big.png" and max(Image.open(out).size) == MIN_SCAN_SIDE
    assert _enlarge_if_small(d / "big.png", d / "unused.png") == d / "big.png"     # large photos untouched


def test_misread_ac_heading_still_reads_the_values():
    # A re-saved photo of a real Fuji label OCR'd the heading as "AR CONDITIONER", and every value was dropped.
    from app.label_ocr import extract_fields
    for heading in ("AR CONDITIONER", "AIR CONDITONER", "ENERGY EFFICIENCY LABEL"):
        lines = [{"text": heading, "bbox": [0, 0, 100, 10]}, {"text": "COOLING", "bbox": [0, 50, 60, 60]},
                 {"text": "5.28", "bbox": [70, 50, 100, 60]}]
        fields = extract_fields(lines)
        assert fields["appliance_type"] == "Air conditioner", heading
        assert float(fields["cooling_capacity_kw"]) == 5.28, heading
    fridge = [{"text": "REFRIGERATOR", "bbox": [0, 0, 100, 10]}]
    assert extract_fields(fridge)["appliance_type"] == "Refrigerator"


def test_appliance_analysis_matches_the_notebook():
    from app.label_ocr import appliance_analysis
    full = appliance_analysis("Air conditioner", "B", 3941.0, 18000.0)
    assert full["grade_meaning"] == "This AC has a high efficiency level, just below A."
    assert full["annual_kwh_explanation"].startswith("This represents the estimated annual electricity consumption")
    assert full["cooling_capacity_explanation"] == "This indicates how much cooling the AC can provide."
    assert full["tip"].startswith("Consider the AC's efficiency grade and annual electricity consumption")
    partial = appliance_analysis("Air conditioner", "B", None, 48000.0)       # yearly kWh not read
    assert partial["annual_kwh_explanation"] is None
    assert partial["tip"] == ("Consider the AC's efficiency grade when choosing a model. "
                              "Make sure its cooling capacity meets your cooling needs.")
    none = appliance_analysis("Air conditioner", None, None, None)
    assert none["grade_meaning"] == "The efficiency grade could not be determined reliably."
    assert none["tip"] == "Review the AC's energy label and specifications before purchasing."


if __name__ == "__main__":
    if TestClient is None:
        print("SKIP test_api (run with the backend virtualenv: .venv/bin/python -m tests.test_api)")
    else:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_"):
                fn()
                print("PASS", name)
