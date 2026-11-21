"""Run:  python -m tests.test_profiles   (uses real Usage sample rows)"""
from app import profiles
from app.profiles import build_profile

HOUSEHOLD = {"region": "Riyadh", "housingType": "Villa", "numberOfResidents": 7, "cookingFuel": "Gas",
             "acType": "Window", "hasInsulation": False, "homeSize": "225", "homeName": "x", "user_id": "SECRET"}
USAGE = {"ac_set_temp": None, "ac_operating_times": 10, "ac_off_for_one_hour": None, "ac_off_when_leaving": 4,
         "applies_energy_tips": True, "home_occupancy_time": 5, "cooling_alternatives": "Desert cooler",
         "encouraged_by_family": 5, "energy_price_pressure": 4, "energy_saving_interest": 2,
         "home_improvement_interest": 4, "indoor_thermal_adjustment": None, "willing_to_upgrade_appliance": False}


def test_no_identifiers_leak():
    p = build_profile(HOUSEHOLD, USAGE)
    assert "SECRET" not in str(p) and "user_id" not in p and "homeName" not in p


def test_questionnaire_values_become_the_evaluated_wording():
    p = build_profile(HOUSEHOLD, USAGE)               # USAGE = a real row from the database
    assert p["builtUpArea"] == 225.0
    assert p["willingToUpgradeAppliance"] == "No" and p["appliesEnergyTips"] == "Yes"
    assert p["acOperatingTimes"] == "10 hours per day" and p["homeOccupancyTime"] == "5 hours per day"
    assert p["indoorThermalAdjustment"] == "Desert cooler"
    assert p["acOffWhenLeaving"] == "Always"                 # 4
    assert p["energySavingInterest"] == "Somewhat interested"  # 2
    assert p["energyPricePressure"] == "Always"              # 4
    assert p["homeImprovementInterest"] == "Always"          # 4
    assert p["encouragedByFamily"] == "Strongly agree"       # 5
    assert p["acSetTemp"] is None and p["acOffForOneHour"] is None   # never collected by the app


def test_every_option_the_app_can_save_has_a_label():
    expected = {"energySavingInterest": {1, 2, 3}, "energyPricePressure": {1, 2, 3, 4},
                "homeImprovementInterest": {1, 2, 3, 4}, "acOffWhenLeaving": {1, 2, 3, 4},
                "encouragedByFamily": {1, 2, 3, 4, 5}}
    for key, values in expected.items():
        assert set(profiles.LABELS[key]) == values, key


def test_numeric_column_returned_as_float_still_maps():
    assert build_profile(HOUSEHOLD, {**USAGE, "energy_saving_interest": 3.0})["energySavingInterest"] == "Very interested"


def test_unknown_value_is_withheld_not_passed_raw():
    assert build_profile(HOUSEHOLD, {**USAGE, "energy_price_pressure": 9})["energyPricePressure"] is None


def test_missing_usage_row():
    p = build_profile(HOUSEHOLD, None)
    assert p["region"] == "Riyadh" and p["acOperatingTimes"] is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
