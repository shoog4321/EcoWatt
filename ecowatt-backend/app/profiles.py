"""Build the household profile the model sees, from your real Household + Usage rows.

The evaluation fed the model survey TEXT answers; the app stores numbers. Rules here:
  * booleans            -> "Yes" / "No"
  * hours per day       -> "N hours per day"            (truthful, but not the evaluated wording)
  * set temperature     -> "N°C"
  * cooling_alternatives (free text) -> indoorThermalAdjustment, as-is   [assumption: verify]
  * ordinal scales (1-4, 1-5 ...) -> the label from LABELS; a value without a label becomes None
    (= "unknown" to the model). A bare "4" would be uninterpretable, so it is never passed through.

Known gaps between the app and the evaluated input (cannot be fixed on the backend):
  * acSetTemp, acOffForOneHour, indoorThermalAdjustment are never collected by the app's questionnaire
    (the Usage columns exist but stay NULL), so they are sent as unknown. The app asks ONE "leave for 1 hour"
    question; it is stored in ac_off_when_leaving and sent as acOffWhenLeaving.
  * homeOccupancyTime / acOperatingTimes: the app stores hours per day, the evaluation used text buckets.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger("ecowatt.profile")

STRUCTURAL = ("region", "housingType", "numberOfResidents", "cookingFuel", "acType", "hasInsulation")

BOOL = {"appliesEnergyTips": "applies_energy_tips", "willingToUpgradeAppliance": "willing_to_upgrade_appliance",
        "acOffForOneHour": "ac_off_for_one_hour"}
HOURS = {"homeOccupancyTime": "home_occupancy_time", "acOperatingTimes": "ac_operating_times"}
ORDINAL = {"acOffWhenLeaving": "ac_off_when_leaving", "energySavingInterest": "energy_saving_interest",
           "energyPricePressure": "energy_price_pressure", "homeImprovementInterest": "home_improvement_interest",
           "encouragedByFamily": "encouraged_by_family"}

# Value the Flutter app saves -> option text shown to the user. Copied from
# lib/screens/behavior_information_screen.dart; these are also the answer wordings that appear in the
# evaluation payload ("Very interested", "Always", "Strongly agree" ...).
_FREQUENCY = {4: "Always", 3: "Usually", 2: "Sometimes", 1: "Never"}
LABELS: dict[str, dict[int, str]] = {
    "energySavingInterest": {3: "Very interested", 2: "Somewhat interested", 1: "Not interested"},
    "energyPricePressure": dict(_FREQUENCY),
    "homeImprovementInterest": dict(_FREQUENCY),
    "acOffWhenLeaving": dict(_FREQUENCY),
    "encouragedByFamily": {5: "Strongly agree", 4: "Agree", 3: "Neutral", 2: "Disagree", 1: "Strongly disagree"},
}

_warned: set[str] = set()


def _warn_once(key: str, msg: str) -> None:
    if key not in _warned:
        _warned.add(key)
        log.warning(msg)


def _num_text(v: float, suffix: str) -> str:
    return f"{v:g}{suffix}"


def _area(text) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", str(text or ""))
    return float(m.group()) if m else None


def build_profile(household: dict, usage: dict | None) -> dict:
    """No names, no IDs: only what the model may see."""
    u = usage or {}
    p: dict = {k: household.get(k) for k in STRUCTURAL}
    p["builtUpArea"] = _area(household.get("homeSize"))

    for key, col in BOOL.items():
        v = u.get(col)
        p[key] = None if v is None else ("Yes" if v else "No")
    for key, col in HOURS.items():
        v = u.get(col)
        p[key] = None if v is None else _num_text(float(v), " hours per day")
    for key, col in ORDINAL.items():
        v = u.get(col)
        table = LABELS.get(key)
        if v is None:
            p[key] = None
        elif table and int(float(v)) in table:
            p[key] = table[int(float(v))]
        else:
            _warn_once(key, f"{key} has no LABELS mapping; withholding stored value {v!r} from the model")
            p[key] = None
    t = u.get("ac_set_temp")
    p["acSetTemp"] = None if t is None else _num_text(float(t), "°C")
    p["indoorThermalAdjustment"] = u.get("cooling_alternatives")   # assumption, see module docstring
    return p
