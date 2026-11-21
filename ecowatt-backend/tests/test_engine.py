"""Run:  python -m tests.test_engine   (no GPU, no network, stdlib only)"""
import asyncio
import json
from pathlib import Path

from app.advice_engine import AdviceEngine, CatalogItem, advice_schema
from app.safety import SafetyRules

DATA = Path(__file__).resolve().parent.parent / "data"

CATALOG = {
    f"ADV_{n:03d}": CatalogItem(f"ADV_{n:03d}", "cooling", f"Title {n}", f"Approved advice {n}.")
    for n in (1, 4, 9, 12, 20, 30, 40, 60)
}
PROFILE = {"region": "Riyadh", "acType": "Window"}
PERIOD = {"month": 10, "year": 2026, "season": "rest_of_year"}
ANALYSIS = {"consumption_level": "High", "drivers": ["Low efficiency AC"]}


def reply(*pairs):
    return json.dumps({"advice": [{"advice_id": a, "personalized_advice": t} for a, t in pairs]})


class FakeLLM:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    async def complete_json(self, messages, schema, max_tokens=640):
        self.calls.append({"messages": messages, "schema": schema, "max_tokens": max_tokens})
        return self.replies.pop(0)


def run(llm):
    engine = AdviceEngine(llm, CATALOG, "SYSTEM", SafetyRules.load(DATA))
    return asyncio.run(engine.generate(case_id="c1", profile=PROFILE, period=PERIOD,
                                       analysis=ANALYSIS, first_name="Sara", last_name="Alharbi"))


def test_clean_run_has_no_name_prefix():
    llm = FakeLLM(reply(("ADV_001", "Set the AC to 24 degrees."), ("ADV_020", "Switch to LED lamps."),
                        ("ADV_030", "Seal gaps around windows.")))
    res = run(llm)
    assert len(llm.calls) == 1
    assert res.items[0]["personalized_advice"] == "Set the AC to 24 degrees."
    assert not any("Sara" in i["personalized_advice"] for i in res.items)
    assert [a["safety"] for a in res.audit] == ["ok"] * 3


def test_safety_repair_used_when_it_works():
    llm = FakeLLM(
        reply(("ADV_001", "Tip one."), ("ADV_009", "Make sure your split AC is properly sized."), ("ADV_020", "Tip.")),
        reply(("ADV_009", "When buying or replacing an AC, make sure it is properly sized.")),
    )
    res = run(llm)
    assert res.audit[1]["safety"] == "repaired"
    assert "buying or replacing" in res.items[1]["personalized_advice"]
    assert llm.calls[1]["schema"]["properties"]["advice"]["items"]["properties"]["advice_id"]["enum"] == ["ADV_009"]


def test_prefix_fallback_for_adv_004():
    llm = FakeLLM(
        reply(("ADV_001", "Tip."), ("ADV_004", "Clean the AC filters every month."), ("ADV_020", "Tip.")),
        reply(("ADV_004", "Clean the AC filters every month.")),  # repair doesn't fix it
    )
    res = run(llm)
    assert res.audit[1]["safety"] == "prefixed"
    assert res.items[1]["personalized_advice"].startswith("If the filters are serviceable, clean")


def test_unresolved_keeps_original_never_worse():
    llm = FakeLLM(
        reply(("ADV_001", "Tip."), ("ADV_012", "Turn lights off."), ("ADV_020", "Tip.")),
        reply(("ADV_012", "Turn lights off.")),  # still missing, and ADV_012 has no prefix
    )
    res = run(llm)
    assert res.audit[1]["safety"] == "unresolved"
    assert res.items[1]["personalized_advice"] == "Turn lights off."


def test_duplicates_trigger_list_repair():
    llm = FakeLLM(
        reply(("ADV_001", "a"), ("ADV_001", "b"), ("ADV_020", "c")),                       # only 2 unique
        reply(("ADV_001", "a"), ("ADV_020", "c"), ("ADV_030", "d"), ("ADV_040", "e")),     # fixed
    )
    res = run(llm)
    assert len(llm.calls) == 2 and len(res.items) == 4
    assert "duplicated" in llm.calls[1]["messages"][-1]["content"]


def test_top_up_when_repair_still_short():
    llm = FakeLLM(
        reply(("ADV_001", "a")),
        reply(("ADV_001", "a"), ("ADV_020", "c")),
        reply(("ADV_030", "d")),  # top-up
    )
    res = run(llm)
    assert len(res.items) == 3
    enum = llm.calls[2]["schema"]["properties"]["advice"]["items"]["properties"]["advice_id"]["enum"]
    assert "ADV_001" not in enum and "ADV_020" not in enum


def test_name_leak_and_unknown_ids_are_dropped():
    llm = FakeLLM(
        reply(("ADV_001", "Sara should set the AC to 24."), ("ADV_999", "x"), ("ADV_020", "b")),
        reply(("ADV_001", "Set the AC to 24."), ("ADV_020", "b"), ("ADV_030", "c")),
    )
    res = run(llm)
    assert len(res.items) == 3 and "Alharbi" not in json.dumps(res.items)


def test_schema_never_demands_more_items_than_ids():
    s = advice_schema(["ADV_001", "ADV_002"], 3, 6)
    assert s["properties"]["advice"]["minItems"] == 2 and s["properties"]["advice"]["maxItems"] == 2


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"\n{len(tests)} passed")
