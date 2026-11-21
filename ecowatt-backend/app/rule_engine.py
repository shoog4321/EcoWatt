"""Component A: SaudiElectricityAnalyzer (rule-based analysis), ported to stdlib Python for ONE bill.

Source: EcoWatt_Energy_Analysis_&_Advice_Personalization_System_v3.ipynb, section 2 (`analyze_household`) and
section 3.1 (the per-bill case that is fed to the model). The arithmetic is unchanged; only pandas/numpy were
replaced, so the backend stays dependency-free.

Contract (consumed by app/main.py and app/jobs.py):
    month, year, season ("winter" | "rest_of_year"), consumption_level ("High" | "Moderate" | "Average" | "Low"),
    comparison_percentage (float | None), drivers (list[str]), message (str), actual_kwh, similar_homes_kwh
    (float | None), saving_sar, saving_kwh (= actual_kwh - optimized_kwh, >= 0), comparison_available (bool)

Inputs (already validated by app/bills.py):
    bill      - {"bill_id", "month": int, "year": int, "kwh": float, "price_sar": float}
    household - raw "Household" row (region, housingType, homeSize, acType, hasInsulation, numberOfResidents, ...)
    history   - unused: the notebook analyses every bill independently of the others
    baselines - rows of consumption_baselines (columns as in household_consumption_baseline.csv:
                region, season, housing_type, *_hours_per_week, insulation_yes_pct, ...)

Differences from the notebook, all for inputs the notebook never saw:
    * builtUpArea comes from Household.homeSize (the notebook's CSV had none, so it always used its 150 m² fallback)
    * numberOfResidents missing -> 4 (the value at which both occupancy adjustments are neutral)
    * no matching baseline (e.g. housingType 'Other') -> comparison_available=False, as the notebook does
"""
from __future__ import annotations

import re

# --- constants copied from the notebook -----------------------------------------------------------------------
WINTER_MONTHS = {12, 1, 2}                       # user_profile.csv: Dec-Feb = Winter, everything else Rest_of_Year
DEFAULT_AREA_M2 = 150.0
WEEKS_PER_MONTH = 4.345
MIN_BASELINE_KWH = 200.0
MAX_REDUCTION = 0.25

AC_POWER_KW = {"window": 3.2, "central": 2.6}    # default (split / other) 2.2
SPLIT_AC_POWER_KW = 2.2
P_HEATER, P_WATER_HEATER = 1.5, 2.0
P_LAMP_REG, P_LAMP_SAV, P_FRIDGE, P_FREEZER = 0.06, 0.009, 0.15, 0.12

REGION_SENSITIVITY = {                           # KAPSARC: % increase in cooling demand per °C
    "riyadh": 0.083, "qassim": 0.083, "hail": 0.083,
    "makkah": 0.129, "madinah": 0.129, "tabuk": 0.129,
    "aseer": 0.103, "jazan": 0.103, "najran": 0.103, "al-baha": 0.103,
    "eastern region": 0.048,
    "northern borders": 0.083, "al-jouf": 0.083,
}


def estimate_cost(kwh: float) -> float:
    base = kwh * 0.18 if kwh <= 6000 else 6000 * 0.18 + (kwh - 6000) * 0.30
    return base * 1.15 + 15


def season_for_month(month: int) -> str:
    return "winter" if month in WINTER_MONTHS else "rest_of_year"


# --- input normalisation ---------------------------------------------------------------------------------------
def _key(v) -> str:
    return str(v or "").strip().lower()


def _row(baseline: dict) -> dict:
    return {str(k).strip().lower(): v for k, v in baseline.items()}


def _num(v, default: float | None = None) -> float | None:
    try:
        return float(v) if v is not None and str(v).strip() != "" else default
    except (TypeError, ValueError):
        return default


def _bool(v) -> bool:
    # notebook: replace 'TRUE'/'True'/'FALSE'/'False' then astype(bool)
    if isinstance(v, str):
        return v.strip().lower() in {"true", "t", "yes", "y", "1"}
    return bool(v)


def _area(home_size) -> float:
    m = re.search(r"\d+(?:\.\d+)?", str(home_size or ""))
    area = float(m.group()) if m else 0.0
    return area if area > 0 else DEFAULT_AREA_M2


def find_baseline(baselines: list[dict], region: str, season: str, housing_type: str) -> dict | None:
    want = (_key(region), _key(season), _key(housing_type))
    for b in baselines:
        r = _row(b)
        if (_key(r.get("region")), _key(r.get("season")), _key(r.get("housing_type"))) == want:
            return r
    return None


# --- analysis ----------------------------------------------------------------------------------------------------
def _baseline_kwh(b: dict, *, region: str, ac_type: str, area: float, residents: float) -> float:
    h = lambda col: _num(b.get(col), 0.0)                                  # noqa: E731

    ac_units = max(round(area * 0.75 / 25), 1)                             # np.round = round-half-even, like round()
    if ac_type == "window":
        ac_hours = h("window_ac_hours_per_week")
    elif ac_type == "central":
        ac_hours = h("central_ac_hours_per_week")
    else:
        ac_hours = h("split_ac_hours_per_week")
    ac_usage = ac_hours * AC_POWER_KW.get(ac_type, SPLIT_AC_POWER_KW) * ac_units

    heater_usage = h("radiant_heater_hours_per_week") * P_HEATER * (area / DEFAULT_AREA_M2)
    base = (h("water_heater_hours_per_week") * P_WATER_HEATER
            + h("regular_lamps_hours_per_week") * P_LAMP_REG
            + h("energy_saving_lamps_hours_per_week") * P_LAMP_SAV
            + h("refrigerator_hours_per_week") * P_FRIDGE
            + h("freezer_hours_per_week") * P_FREEZER)

    ins = _num(b.get("insulation_yes_pct"))
    insulation_rate = ins / 100 if ins is not None else 0.5
    region_factor = 1 + REGION_SENSITIVITY.get(region, 0.0)
    insulation_factor = 1 - insulation_rate * 0.15

    weekly = ac_usage * region_factor * insulation_factor + heater_usage * insulation_factor + base
    occupancy = min(max(1 + (residents - 4) * 0.015, 0.95), 1.15)
    return max(weekly * occupancy * WEEKS_PER_MONTH, MIN_BASELINE_KWH)


def _reduction(*, has_insulation: bool, ac_type: str, residents: float) -> float:
    r1 = 0.03
    r2 = 0.0 if has_insulation else 0.15
    r3 = {"window": 0.08, "central": 0.03}.get(ac_type, 0.0)
    r4 = min(max((residents - 4) * 0.02, 0.0), 0.05)
    return min(1 - (1 - r1) * (1 - r2) * (1 - r3) * (1 - r4), MAX_REDUCTION)


def _classify(actual: float, baseline: float) -> tuple[float, str, str]:
    diff = (actual - max(baseline, 1)) / max(baseline, 1) * 100
    if diff > 20:
        return diff, "High", f"Significantly above similar homes (+{diff:.0f}%)"
    if diff > 5:
        return diff, "Moderate", f"Slightly above similar homes (+{diff:.0f}%)"
    if diff < -10:
        return diff, "Low", f"Efficient compared to similar homes (-{abs(diff):.0f}%)"
    return diff, "Average", "Within the average range of similar homes"


def analyze_bill(*, bill: dict, household: dict, history: list[dict], baselines: list[dict]) -> dict:
    month, year, kwh = int(bill["month"]), int(bill["year"]), float(bill["kwh"])
    season = season_for_month(month)
    region = _key(household.get("region"))
    ac_type = _key(household.get("acType"))
    has_insulation = _bool(household.get("hasInsulation"))
    residents = _num(household.get("numberOfResidents"), 4.0)
    area = _area(household.get("homeSize"))

    b = find_baseline(baselines, region, season, household.get("housingType"))
    similar = _baseline_kwh(b, region=region, ac_type=ac_type, area=area, residents=residents) if b else None

    optimized = kwh * (1 - _reduction(has_insulation=has_insulation, ac_type=ac_type, residents=residents))
    saving_sar = max(estimate_cost(kwh) - estimate_cost(optimized), 0.0)

    drivers: list[str] = []
    if similar is None:
        diff, level, message = None, "Average", "No baseline available"
    else:
        if not has_insulation:
            drivers.append("Poor insulation")
        if ac_type == "window":
            drivers.append("Low efficiency AC")
        if residents >= 6:
            drivers.append("High occupancy")
        diff, level, message = _classify(kwh, similar)

    return {
        "month": month,
        "year": year,
        "season": season,
        "consumption_level": level,
        "comparison_percentage": round(diff, 2) if diff is not None else None,
        "drivers": drivers,
        "message": message,
        "actual_kwh": round(kwh, 2),
        "similar_homes_kwh": round(similar, 2) if similar is not None else None,
        "saving_sar": round(saving_sar, 2),
        "saving_kwh": round(max(kwh - optimized, 0.0), 2),
        "comparison_available": similar is not None,
    }
