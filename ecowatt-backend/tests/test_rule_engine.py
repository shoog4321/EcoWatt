"""Run:  python -m tests.test_rule_engine   (stdlib only)

Golden values were produced by the notebook's SaudiElectricityAnalyzer (pandas) on the same inputs; the port was
also checked against it on all 42 bills of user_profile.csv and 600 random households (0 mismatches).
"""
from pathlib import Path

from tests import _httpx_stub  # noqa: F401

from app.advice_engine import load_catalog
from app.jobs import CATEGORIES, CATEGORY_ALIASES
from app.rule_engine import analyze_bill, season_for_month


COLS = ("region,season,housing_type,average_temp_c,window_ac_hours_per_week,split_ac_hours_per_week,"
        "central_ac_hours_per_week,radiant_heater_hours_per_week,water_heater_hours_per_week,"
        "regular_lamps_hours_per_week,energy_saving_lamps_hours_per_week,refrigerator_hours_per_week,"
        "freezer_hours_per_week,insulation_yes_pct,cooking_gas_pct,cooking_elec_pct").split(",")
ROWS = """Riyadh,Rest_of_Year,Villa,31.9,72.9,85.6,79.6,1,20.8,65.2,84.1,168,167.3,43.1,80.6,19.4
Makkah,Rest_of_Year,Traditional House,32.2,92.8,85.9,89.4,1.4,35.3,100.7,89,168,167.3,47.3,99.8,0
Eastern Region,Winter,Apartment,19.1,5.1,7.8,11.6,21,86.5,53.2,62.2,168,166.6,53.3,60.8,38.2"""
BASELINES = [dict(zip(COLS, (v if i < 3 else float(v) for i, v in enumerate(line.split(","))))) for line in ROWS.splitlines()]


def run(household, month, kwh):
    return analyze_bill(bill={"bill_id": "b", "month": month, "year": 2026, "kwh": kwh, "price_sar": 1.0},
                        household=household, history=[], baselines=BASELINES)


def test_window_ac_uninsulated_large_household():
    a = run({"region": "Riyadh", "housingType": "Villa", "acType": "Window", "hasInsulation": False,
             "numberOfResidents": 7, "homeSize": "225"}, 7, 9800.0)
    assert a["season"] == "rest_of_year" and a["consumption_level"] == "High"
    assert (a["comparison_percentage"], a["similar_homes_kwh"], a["saving_sar"], a["saving_kwh"]) == \
        (23.49, 7935.98, 845.25, 2450.0)
    assert a["drivers"] == ["Poor insulation", "Low efficiency AC", "High occupancy"]
    assert a["comparison_available"] and a["message"] == "Significantly above similar homes (+23%)"


def test_winter_split_apartment():
    a = run({"region": "Eastern Region", "housingType": "Apartment", "acType": "Split", "hasInsulation": True,
             "numberOfResidents": 3, "homeSize": "120 m²"}, 1, 900.0)
    assert a["season"] == "winter" and a["consumption_level"] == "Low" and a["drivers"] == []
    assert (a["comparison_percentage"], a["similar_homes_kwh"], a["saving_sar"], a["saving_kwh"]) == \
        (-32.45, 1332.36, 5.59, 27.0)


def test_central_ac():
    a = run({"region": "Makkah", "housingType": "Traditional House", "acType": "Central", "hasInsulation": "TRUE",
             "numberOfResidents": 5, "homeSize": 300}, 8, 5200.0)
    assert (a["consumption_level"], a["comparison_percentage"], a["similar_homes_kwh"], a["saving_sar"],
            a["saving_kwh"]) == ("Low", -49.2, 10235.45, 83.87, 405.17)


def test_no_baseline_for_other_housing_type():
    a = run({"region": "Riyadh", "housingType": "Other", "acType": "Window", "hasInsulation": False,
             "numberOfResidents": 7}, 7, 9800.0)
    assert a["comparison_available"] is False and a["similar_homes_kwh"] is None
    assert a["comparison_percentage"] is None and a["drivers"] == [] and a["consumption_level"] == "Average"
    assert a["saving_kwh"] == 2450.0 and a["saving_sar"] == 845.25      # savings do not depend on the baseline


def test_seasons():
    assert [season_for_month(m) for m in (12, 1, 2, 3, 11)] == ["winter"] * 3 + ["rest_of_year"] * 2


def test_handoff_catalog_loads_and_maps_to_enum():
    cat = load_catalog(Path(__file__).resolve().parent.parent / "data" / "advice_catalog.json")
    assert len(cat) >= 50 and cat["ADV_004"].advice.startswith("Monthly cleaning")
    for item in cat.values():
        assert CATEGORY_ALIASES.get(item.type.lower(), item.type.lower()) in CATEGORIES, item


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
