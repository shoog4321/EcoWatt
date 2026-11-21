"""Backend post-checks on the GPU service's answer.  Run:  python -m tests.test_remote_engine"""
import asyncio
import types

from tests import _httpx_stub  # noqa: F401

from app.advice_engine import AdviceGenerationError, CatalogItem
from app.remote_engine import RemoteAdviceEngine

SHA = "a" * 64
CATALOG = {f"ADV_{n:03d}": CatalogItem(f"ADV_{n:03d}", "cooling", f"Title {n}", f"Advice {n}.") for n in range(1, 9)}


class FakeGpu:
    def __init__(self, advice, audit=None, sha=SHA):
        self.base_url = "x"
        self._resp = {"advice": advice, "audit": audit if audit is not None else [
            {"advice_id": a["advice_id"], "safe": True} for a in advice], "catalog_sha256": sha}

    async def generate(self, profile, period, analysis, exclude_ids=None):
        self.sent = (profile, period, analysis)
        self.exclude_ids = exclude_ids
        return self._resp


def item(n, text=None):
    return {"advice_id": f"ADV_{n:03d}", "personalized_advice": text or f"Do thing {n}."}


def run(gpu, first="Sara", last="Alharbi"):
    eng = RemoteAdviceEngine(gpu, CATALOG, SHA)
    return asyncio.run(eng.generate(case_id="c", profile={"region": "Riyadh"}, period={}, analysis={},
                                    first_name=first, last_name=last))


def test_happy_path_no_name_and_titles():
    res = run(FakeGpu([item(1, "Set the AC to 24."), item(2), item(3)]))
    assert res.items[0]["personalized_advice"] == "Set the AC to 24."
    assert not any("Sara" in i["personalized_advice"] for i in res.items)
    assert res.items[1]["title"] == "Title 2" and res.items[1]["type"] == "cooling"
    assert [a["safety"] for a in res.audit] == ["ok"] * 3


def test_duplicates_unknown_ids_and_name_leaks_are_dropped():
    gpu = FakeGpu([item(1), item(1), {"advice_id": "ADV_999", "personalized_advice": "x"},
                   item(2, "Sara should switch it off."), item(3), item(4), item(5)])
    res = run(gpu)
    assert [i["advice_id"] for i in res.items] == ["ADV_001", "ADV_003", "ADV_004", "ADV_005"]
    assert sum(1 for a in res.audit if "dropped" in a) == 3


def test_too_few_valid_items_is_a_content_failure():
    try:
        run(FakeGpu([item(1), item(1), item(2)]))
        raise AssertionError("expected AdviceGenerationError")
    except AdviceGenerationError as e:
        assert "Only 2 valid" in str(e)


def test_more_than_six_is_trimmed():
    assert len(run(FakeGpu([item(n) for n in range(1, 9)])).items) == 6


def test_unconfirmed_safety_is_flagged_but_item_kept():
    gpu = FakeGpu([item(1), item(2), item(3)], audit=[{"advice_id": "ADV_001", "safe": True},
                                                      {"advice_id": "ADV_002", "safe": False},
                                                      {"advice_id": "ADV_003", "safe": True}])
    res = run(gpu)
    assert len(res.items) == 3 and [a["safety"] for a in res.audit] == ["ok", "unresolved", "ok"]


def test_catalog_drift_between_gpu_and_backend_is_rejected():
    try:
        run(FakeGpu([item(1), item(2), item(3)], sha="b" * 64))
        raise AssertionError("expected AdviceGenerationError")
    except AdviceGenerationError as e:
        assert "different advice_catalog.json" in str(e)


def test_no_name_means_no_prefix():
    assert run(FakeGpu([item(1, "Set it."), item(2), item(3)]), first="", last="").items[0]["personalized_advice"] == "Set it."




def test_winter_only_item_dropped_on_summer_bill():
    from app.advice_engine import CatalogItem
    import app.remote_engine as R
    cat = dict(CATALOG)
    cat["ADV_002"] = CatalogItem("ADV_002", "heating", "", "In winter, lower the heating thermostat.", "winter")
    items, errors = R.check_items([{"advice_id": "ADV_002", "personalized_advice": "x"},
                                   {"advice_id": "ADV_001", "personalized_advice": "y"}], cat, [], season="rest_of_year")
    assert [i["advice_id"] for i in items] == ["ADV_001"] and "winter-only" in errors[0]
    items, _ = R.check_items([{"advice_id": "ADV_002", "personalized_advice": "x"}], cat, [], season="winter")
    assert [i["advice_id"] for i in items] == ["ADV_002"]


def test_excluded_ids_are_sent_and_dropped_if_returned():
    gpu = FakeGpu([item(1), item(2), item(3), item(4)])
    eng = RemoteAdviceEngine(gpu, CATALOG, SHA)
    res = asyncio.run(eng.generate(case_id="c", profile={}, period={}, analysis={},
                                   exclude_ids=frozenset({"ADV_002"})))
    assert gpu.exclude_ids == ["ADV_002"]
    assert [i["advice_id"] for i in res.items] == ["ADV_001", "ADV_003", "ADV_004"]
    assert any("excluded" in a.get("dropped", "") for a in res.audit)


def test_excluded_ids_rules():
    from app.advice_engine import excluded_ids
    cat = {f"A{n}": CatalogItem(f"A{n}", "cooling", "", "x", "winter" if n == 0 else "all", n in (1, 2))
           for n in range(12)}
    summer_no = excluded_ids(cat, season="rest_of_year", willing_to_upgrade="No", applied={"A5", "A6"})
    assert summer_no == {"A0", "A1", "A2", "A5", "A6"}
    assert excluded_ids(cat, season="winter", willing_to_upgrade="Yes", applied=set()) == set()
    assert excluded_ids(cat, season="winter", willing_to_upgrade=None, applied={"A3"}) == {"A3"}
    # applied tips come back once too few others are left
    many = {f"A{n}" for n in range(3, 12)}
    assert excluded_ids(cat, season="rest_of_year", willing_to_upgrade="No", applied=many) == {"A0", "A1", "A2"}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
