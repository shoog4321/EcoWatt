"""Bill-parsing rules of invoice_ocr on recorded OCR output (no OCR model, no torch needed).
Run:  python -m tests.test_invoice_ocr

The fixture is the EasyOCR output for a real SEC residential bill (Aug 2026: 612.46 SAR, 2,903.14 kWh), with the
customer/address block removed. Typical OCR damage it contains: the decimal point read as "0" (2903014), the kWh unit
misread, a second "كمية الاستهلاك" label (chart heading) without a value.
"""
import json
import sys
import types
from pathlib import Path

for name in ("cv2", "torch", "easyocr"):               # parsing does not need the OCR stack
    sys.modules.setdefault(name, types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False), Reader=lambda *a, **k: None))

from app import invoice_ocr as o  # noqa: E402

LINES = json.loads((Path(__file__).parent / "fixtures" / "sec_bill_residential_ocr_lines.json").read_text(encoding="utf-8"))


def analyze(lines):
    o.extract_ocr_lines = lambda path: lines
    return o.analyze_bill("unused.png")


def test_residential_bill_all_fields_and_tariff_verified():
    r = analyze(LINES)
    assert (r["month"], r["amount_due"], r["consumption"]) == ("August 2026", 612.46, 2903.14)
    assert r["status"] == "complete" and r["verified"] is True


def test_number_right_after_label_survives_a_misread_unit():
    line = ["إجمالي الاستهلاك : 2903014 95س 46 6120"]
    assert 2903.14 in o.extract_value_after_keyword(line, ["إجمالي الاستهلاك"], o.CONSUMPTION_RANGE)


def test_label_without_value_falls_through_to_the_next_match():
    lines = ["كمية الأستهلاك السربحة الاولى", "بيانات", "كمية الاستهلال : 2902,14"]
    assert o.extract_value_after_keyword(lines, ["كمية الاستهلاك"], o.CONSUMPTION_RANGE) == [2902.14]


def test_meter_reading_difference():
    lines = ["قراءة بداية الفترة: 6 2 , 40605", "قراءة نهاية الفترة : 0 4 ,43508"]
    assert o.meter_reading_difference(lines, o.CONSUMPTION_RANGE) == [2903.14]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
