"""Run:  python -m tests.test_bills   (uses the real sample rows from your Supabase)"""
from app.bills import BillDataError, normalize_bill, recent_history, tariff_problem

ROWS = [  # newest first, exactly as returned by your database
    {"bill_id": "a", "year": "2026", "month": "September", "price": 657.32, "consumption": 72119.91, "createdAt": "5"},
    {"bill_id": "b", "year": "2026", "month": "August", "price": 1007, "consumption": 1.07, "createdAt": "4"},
    {"bill_id": "c", "year": "2026", "month": "August", "price": 1007, "consumption": 1.07, "createdAt": "3"},
    {"bill_id": "d", "year": "2025", "month": "August", "price": 700, "consumption": 1300, "createdAt": "2"},
    {"bill_id": "e", "year": "2025", "month": "July", "price": 244, "consumption": 300, "createdAt": "1"},
]


def test_sample_bills_that_fail_the_tariff_rule():
    bad = [r["bill_id"] for r in ROWS if tariff_problem(float(r["consumption"]), float(r["price"]))]
    assert bad == ["a", "b", "c", "d"]


def test_history_drops_invalid_and_duplicates():
    assert [b["bill_id"] for b in recent_history(ROWS)] == ["e"]


def test_dedupe_keeps_newest_and_sorts_by_period():
    rows = [
        {"bill_id": "n", "year": "2026", "month": "March", "price": 100.0, "consumption": 400, "createdAt": "9"},
        {"bill_id": "o", "year": "2026", "month": "March", "price": 100.0, "consumption": 400, "createdAt": "1"},
        {"bill_id": "p", "year": "2026", "month": "1", "price": 100.0, "consumption": 400, "createdAt": "2"},
    ]
    assert [b["bill_id"] for b in recent_history(rows)] == ["n", "p"]


def test_normalize_errors_and_fallbacks():
    for bad in ({"month": "Foo", "year": "2026", "consumption": 1, "price": 1},
                {"month": "May", "year": "2026", "consumption": None, "price": 10}):
        try:
            normalize_bill(bad)
            raise AssertionError("should have failed")
        except BillDataError:
            pass
    b = normalize_bill({"billing_period": "2026-03-01", "totalKwh": 400, "totalCostSar": 100})
    assert (b["year"], b["month"], b["kwh"]) == (2026, 3, 400.0)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
