"""Bill normalisation and sanity checks (stdlib only).

Your app writes month/year (text) + consumption/price; billing_period, totalKwh and
totalCostSar are never filled, and nothing stops absurd values or duplicates. This module
is the gate before any analysis or LLM call.
"""
from __future__ import annotations

import calendar

MONTHS = {n.lower(): i for i, n in enumerate(calendar.month_name) if n}
MONTHS.update({n.lower(): i for i, n in enumerate(calendar.month_abbr) if n})

# Tariff from the report (4.6.3.3): 0.18 SAR/kWh up to 6,000 kWh, 0.30 above, +15% VAT, +15 SAR meter fee
TIER_LIMIT, RATE_LOW, RATE_HIGH, VAT, METER_FEE = 6000, 0.18, 0.30, 0.15, 15.0
# The report's data-cleaning rule: reject when the deviation exceeds BOTH of these
MAX_ABS_DEV_SAR, MAX_REL_DEV = 200.0, 0.25


class BillDataError(ValueError):
    pass


def parse_month(value) -> int | None:
    s = str(value or "").strip().lower()
    if s.isdigit():
        return int(s) if 1 <= int(s) <= 12 else None
    return MONTHS.get(s)


def _num(*candidates) -> float | None:
    for c in candidates:
        if c is not None:
            try:
                return float(c)
            except (TypeError, ValueError):
                pass
    return None


def normalize_bill(row: dict) -> dict:
    month, year = parse_month(row.get("month")), None
    try:
        year = int(str(row.get("year", "")).strip())
    except ValueError:
        pass
    period = str(row.get("billing_period") or "")
    if (month is None or year is None) and len(period) >= 7:        # fall back to billing_period (YYYY-MM-DD)
        try:
            year, month = int(period[:4]), int(period[5:7])
        except ValueError:
            pass
    kwh, price = _num(row.get("consumption"), row.get("totalKwh")), _num(row.get("price"), row.get("totalCostSar"))
    if month is None or year is None:
        raise BillDataError("Bill has no readable month/year.")
    if kwh is None or kwh <= 0 or price is None or price <= 0:
        raise BillDataError("Bill needs a positive consumption (kWh) and price (SAR).")
    return {"bill_id": row.get("bill_id"), "month": month, "year": year, "kwh": kwh, "price_sar": price,
            "created_at": row.get("createdAt")}


def expected_cost_sar(kwh: float) -> float:
    energy = min(kwh, TIER_LIMIT) * RATE_LOW + max(kwh - TIER_LIMIT, 0) * RATE_HIGH
    return energy * (1 + VAT) + METER_FEE


def tariff_problem(kwh: float, price: float) -> str | None:
    exp = expected_cost_sar(kwh)
    dev = abs(price - exp)
    if dev > MAX_ABS_DEV_SAR and dev / exp > MAX_REL_DEV:
        return (f"{kwh:g} kWh should cost about {exp:.0f} SAR under the residential tariff, "
                f"but the bill says {price:g} SAR. One of the two values is probably wrong.")
    return None


def recent_history(rows_newest_first: list[dict], n: int = 6) -> list[dict]:
    """Up to n valid, tariff-consistent bills, one per (year, month), newest period first."""
    seen, out = set(), []
    for row in rows_newest_first:
        try:
            b = normalize_bill(row)
        except BillDataError:
            continue
        key = (b["year"], b["month"])
        if key in seen or tariff_problem(b["kwh"], b["price_sar"]):
            continue
        seen.add(key)
        out.append(b)
    out.sort(key=lambda b: (b["year"], b["month"]), reverse=True)
    return out[:n]
