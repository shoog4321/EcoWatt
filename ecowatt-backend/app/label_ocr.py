"""AC energy-label scanner (SASO efficiency label), from EcoWatt_Appliance_Label_OCR_AConly notebook.

Everything down to `analyze_label` is the original notebook code (cell 2, "Load the EcoWatt OCR code"), unchanged.
`analyze_label` runs the same steps as the notebook's scan cell:
    preprocess -> enhance -> efficiency-arrow detection (grade) -> PaddleOCR -> extract_fields
and returns a compact result for the app. Nothing is stored. Additions for the app: small images are
enlarged before scanning, and a few common Saudi-market brands were added to `known_brands`. Notebook evaluation on 10 labels:
grade 100%, cooling kW / BTU / efficiency value 80%, annual kWh 70% -> the app asks users to check the values.

Needs: paddlepaddle==3.0.0, paddleocr==3.7.0 (requirements-label.txt). PP-OCRv5 *mobile* models run on a CPU.
"""
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
import cv2
import numpy as np
# PaddleOCR 3.x is initialized lazily so the API can start and /health can be
# checked even if model initialization fails. The first OCR request may download
# the model files if they are not already cached.
OCR_DET_MODEL = os.getenv("OCR_DET_MODEL", "PP-OCRv5_mobile_det")
OCR_REC_MODEL = os.getenv("OCR_REC_MODEL", "arabic_PP-OCRv5_mobile_rec")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
MIN_LINE_CONFIDENCE = float(os.getenv("MIN_LINE_CONFIDENCE", "0.50"))


_ocr_engine = None
_ocr_init_error = None

def get_ocr_engine():
    """Create the OCR engine once, on the first request."""
    global _ocr_engine, _ocr_init_error

    if _ocr_engine is not None:
        return _ocr_engine

    if _ocr_init_error is not None:
        raise RuntimeError(
            f"OCR initialization previously failed: {_ocr_init_error}"
        )

    try:
        from paddleocr import PaddleOCR

        _ocr_engine = PaddleOCR(
            text_detection_model_name=OCR_DET_MODEL,
            text_recognition_model_name=OCR_REC_MODEL,

            # Give the detector more resolution to find small text.
            text_det_limit_side_len=1280,
            text_det_limit_type="max",

            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

        return _ocr_engine

    except Exception as exc:
        _ocr_init_error = str(exc)
        raise RuntimeError(
            "Could not initialize PaddleOCR. Details: " + str(exc)
        ) from exc

def normalize_digits(text: str) -> str:
    """Normalize Arabic-Indic and Eastern Arabic-Indic digits for matching."""
    translation = str.maketrans(
        "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
        "01234567890123456789",
    )
    return text.translate(translation)


def normalize_text(text: str) -> str:
    text = normalize_digits(text)
    text = text.replace("٫", ".").replace("٬", ",")
    return re.sub(r"\s+", " ", text).strip()



def flatten_paddle_result(result: Any) -> list[dict]:
    """Preserve recognized text, confidence, and text location safely."""

    lines = []

    def as_list(value):
        """Convert arrays and tuples to lists without Boolean evaluation."""
        if value is None:
            return []

        if isinstance(value, np.ndarray):
            return value.tolist()

        if isinstance(value, (list, tuple)):
            return list(value)

        return [value]

    def first_available(payload, keys):
        """Return the first existing, non-None value."""
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return value
        return []

    def get_box(poly):
        if poly is None:
            return None

        try:
            points = np.asarray(poly, dtype=float)

            if points.size == 0:
                return None

            # Format: [x1, y1, x2, y2]
            if points.shape == (4,):
                x1, y1, x2, y2 = points
                return [float(x1), float(y1), float(x2), float(y2)]

            # Format: polygon points
            points = points.reshape(-1, 2)

            return [
                float(points[:, 0].min()),
                float(points[:, 1].min()),
                float(points[:, 0].max()),
                float(points[:, 1].max())
            ]

        except (TypeError, ValueError):
            return None

    # Safely handle the outer result.
    if result is None:
        return lines

    if isinstance(result, np.ndarray):
        result_items = result.tolist()
    elif isinstance(result, (list, tuple)):
        result_items = list(result)
    else:
        result_items = [result]

    for item in result_items:
        payload = None

        if isinstance(item, dict):
            payload = item

        elif hasattr(item, "json"):
            payload = item.json
            if callable(payload):
                payload = payload()

        elif hasattr(item, "to_dict"):
            payload = item.to_dict()

        if isinstance(payload, dict) and isinstance(payload.get("res"), dict):
            payload = payload["res"]

        if isinstance(payload, dict):

            texts = as_list(first_available(
                payload, ["rec_texts", "texts"]
            ))

            scores = as_list(first_available(
                payload, ["rec_scores", "scores"]
            ))

            boxes = as_list(first_available(
                payload, ["rec_polys", "dt_polys", "rec_boxes"]
            ))

            for i, text in enumerate(texts):

                if not isinstance(text, str) or not text.strip():
                    continue

                confidence = None

                if i < len(scores):
                    try:
                        confidence = float(scores[i])
                    except (TypeError, ValueError):
                        pass

                box = get_box(boxes[i]) if i < len(boxes) else None

                line = {
                    "text": text.strip(),
                    "confidence": confidence,
                    "bbox": box
                }

                if box is not None:
                    x1, y1, x2, y2 = box
                    line["center_x"] = (x1 + x2) / 2
                    line["center_y"] = (y1 + y2) / 2

                lines.append(line)

            continue

        # Compatibility with older PaddleOCR output.
        try:
            for entry in item:

                if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                    continue

                recognition = entry[1]

                if not isinstance(recognition, (list, tuple)):
                    continue

                text = recognition[0]

                if not isinstance(text, str) or not text.strip():
                    continue

                confidence = None

                try:
                    confidence = float(recognition[1])
                except (IndexError, TypeError, ValueError):
                    pass

                lines.append({
                    "text": text.strip(),
                    "confidence": confidence,
                    "bbox": get_box(entry[0])
                })

        except TypeError:
            continue

    return lines

def create_ocr_variant(source: Path, destination: Path):
    """Create an enhanced OCR image while preserving the original."""

    image = cv2.imread(str(source))

    if image is None:
        raise ValueError("Could not read source image.")

    enhanced = enhance_for_ocr(image)

    if not cv2.imwrite(str(destination), enhanced):
        raise ValueError("Could not save enhanced image.")


def find_first(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" :：.-")
    return None

def has(pattern, text):
    return bool(re.search(pattern, text, re.I))


def extract_fields(lines: list[dict]) -> dict:
    """Extract appliance-label fields using OCR text and 2D positions."""

    from difflib import SequenceMatcher

    raw_text = "\n".join(str(x.get("text", "")) for x in lines)
    normalized = normalize_text(raw_text)
    lowered = normalized.lower()

    prepared = []

    for line in lines:
        text = normalize_text(str(line.get("text", ""))).strip()
        bbox = line.get("bbox")
        cx = line.get("center_x")
        cy = line.get("center_y")
        width = None
        height = None

        try:
            if hasattr(bbox, "tolist"):
                bbox = bbox.tolist()

            if bbox is not None and len(bbox) == 4:
                x1, y1, x2, y2 = map(float, bbox)
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                width = abs(x2 - x1)
                height = abs(y2 - y1)
        except (TypeError, ValueError):
            pass

        try:
            confidence = float(line.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0

        prepared.append({
            "text": text,
            "confidence": confidence,
            "x": float(cx) if cx is not None else None,
            "y": float(cy) if cy is not None else None,
            "width": width,
            "height": height
        })

    positioned = [
        x for x in prepared
        if x["x"] is not None and x["y"] is not None
    ]

    if positioned:
        min_x = min(x["x"] for x in positioned)
        max_x = max(x["x"] for x in positioned)
        min_y = min(x["y"] for x in positioned)
        max_y = max(x["y"] for x in positioned)

        image_width = max(max_x - min_x, 1)
        image_height = max(max_y - min_y, 1)
    else:
        min_x = min_y = 0
        image_width = image_height = 1000

    # ---------------------------------------
    # Helper functions and numeric preparation
    # ---------------------------------------

    def has(pattern, text):
        return bool(re.search(pattern, text, re.I))

    def find_anchor(pattern):
        for item in prepared:
            if re.search(pattern, item["text"], re.I):
                return item
        return None

    def closest(anchor, candidates, max_x=1.0, max_y=1.0):
        if not candidates or anchor is None:
            return None

        if anchor["x"] is None or anchor["y"] is None:
            return None

        possible = []

        for item in candidates:
            if item["x"] is None or item["y"] is None:
                continue

            dx = abs(item["x"] - anchor["x"]) / image_width
            dy = abs(item["y"] - anchor["y"]) / image_height

            if dx <= max_x and dy <= max_y:
                possible.append((dx + dy, item))

        if not possible:
            return None

        possible.sort(key=lambda x: x[0])
        return possible[0][1]

    def numeric_value(text):
        text = text.strip().strip("()[]{}:;, ")

        if re.fullmatch(r"\d+(?:[.,]\d+)?", text):
            return text.replace(",", ".")

        return None

    numeric_lines = []

    for item in prepared:
        value = numeric_value(item["text"])

        if value is not None:
            numeric_lines.append({
                **item,
                "value": value
            })
        # --------------------------------------------------
    # 1. Appliance type
    # --------------------------------------------------

    appliance_type = None

    if has(r"a?i?r\s*condit(?:i)?on(?:er|ing)|مكيف|مكيفات", lowered):
        appliance_type = "Air conditioner"

    elif has(r"refrigerator|refrigeration|fridge|ثلاجة|ثلاجات", lowered):
        appliance_type = "Refrigerator"

    else:
        # EcoWatt addition: this scanner only supports AC labels. A one-letter OCR slip in the heading
        # ("AR CONDITIONER") used to drop every value on an otherwise readable label.
        appliance_type = "Air conditioner"

    # --------------------------------------------------
    # 2. Brand
    # --------------------------------------------------

    known_brands = [
        "G5 GENERAL SUPREME",
        "GENERALCLASS",
        "GENERAL CLASS",
        "FUJI ELECTRIC",
        "GE APPLIANCES",
        "WINDOW7",
        "WINDOW 7",
        "CRAFFT",
        "ENVIRO",
        "MIDEA",
        "BASIC",
        "TERIM",
        "GREE",
        "FUJI",
        "SAMSUNG",
        "HISENSE",
        "TOSHIBA",
        "SHARP",
        "PANASONIC",
        "CARRIER",
        "DAIKIN",
        "AUX",
        "HAIER",
        "CHIGO",
        "LG",
        "G5",
        # added for the app: other brands common in Saudi Arabia
        "SUPER GENERAL",
        "KELVINATOR",
        "FRIGIDAIRE",
        "ELECTROLUX",
        "WHIRLPOOL",
        "ZAMIL",
        "YORK"
    ]

    brand = None

    # First try exact matches.
    for known in sorted(known_brands, key=len, reverse=True):
        if re.search(
            r"(?<![A-Z0-9])" + re.escape(known) + r"(?![A-Z0-9])",
            raw_text,
            re.I
        ):
            brand = known.upper()
            break

    # Then try fuzzy matching for OCR errors.
    if brand is None:
        for item in prepared:
            candidate = re.sub(
                r"[^A-Z0-9 ]", "", item["text"].upper()
            ).strip()

            if len(candidate) < 5:
                continue

            for known in known_brands:
                known_clean = re.sub(r"[^A-Z0-9 ]", "", known.upper())

                similarity = SequenceMatcher(
                    None, candidate, known_clean
                ).ratio()

                if similarity >= 0.82:
                    brand = known.upper()
                    break

            if brand:
                break

    # Explicit brand heading fallback.
    if brand is None:
        for i, item in enumerate(prepared):
            if has(r"\bBRAND(?:\s+NAME)?\b|العلامة\s+التجارية", item["text"]):
                for candidate in prepared[i + 1:i + 5]:
                    value = candidate["text"].strip()

                    if (
                        re.fullmatch(r"[A-Za-z][A-Za-z0-9 &.-]{1,35}", value)
                        and not has(
                            r"china|country|model|made in|standard|saso",
                            value
                        )
                    ):
                        brand = value.upper()
                        break
                break

    # --------------------------------------------------
    # 3. Model number
    # --------------------------------------------------

    model_number = None

    model_heading = find_anchor(
        r"\bMODEL(?:\s+NUMBER|\s+NO\.?)?\b|"
        r"رقم\s+الطراز|رقم\s+الموديل"
    )

    def valid_model(value):
        value = value.strip(" .,:;")

        if len(value) < 6 or len(value) > 35:
            return False

        if not any(c.isalpha() for c in value):
            return False

        if not any(c.isdigit() for c in value):
            return False

        if has(
            r"SASO|2663|2863|2021|2025|2026|"
            r"^E[A-Z]?\d{3,}|^ED\d{3,}",
            value
        ):
            return False

        return True

    model_candidates = []

    # Support both separated and non-separated model codes.
    model_pattern = re.compile(
        r"\b[A-Z0-9][A-Z0-9./_-]{5,34}\b",
        re.I
    )

    for item in prepared:
        for match in model_pattern.finditer(item["text"]):
            value = match.group(0)

            if valid_model(value):
                model_candidates.append({
                    **item,
                    "value": value
                })

    if model_candidates:
        if model_heading:
            selected = closest(
                model_heading,
                model_candidates,
                max_x=0.55,
                max_y=0.20
            )

            if selected:
                model_number = selected["value"]

        if model_number is None:
            model_candidates.sort(
                key=lambda x: x["confidence"],
                reverse=True
            )
            model_number = model_candidates[0]["value"]

    # --------------------------------------------------
    # 4. Efficiency metric
    # --------------------------------------------------

    metric = None
    metric_value = None

    metric_pattern = re.compile(
        r"\b(SEER|EER|CSPF|AEER|COP)\b",
        re.I
    )

    metric_evidence = None

    for item in prepared:
        match = metric_pattern.search(item["text"])

        if match:
            metric = match.group(1).upper()
            metric_evidence = item
            break

    # --------------------------------------------------
    # 5. Numeric fields
    # --------------------------------------------------

    cooling_kw = None
    cooling_btu = None
    annual_consumption = None

    if appliance_type == "Air conditioner":

        decimals = []
        integers = []

        for item in numeric_lines:
            try:
                value = float(item["value"])
            except ValueError:
                continue

            if "." in item["value"]:
                decimals.append(item)
            elif value.is_integer():
                integers.append(item)

        kw_candidates = [
            x for x in decimals
            if 1.0 <= float(x["value"]) <= 20.0
        ]

        btu_candidates = [
            x for x in integers
            if 8000 <= int(float(x["value"])) <= 60000
        ]

        annual_candidates = [
            x for x in integers
            if 1000 <= int(float(x["value"])) <= 30000
        ]

        capacity_anchor = find_anchor(
            r"\bCOOLING\b|\bCAPACITY\b|التبريد|سعة التبريد"
        )

        annual_anchor = find_anchor(
            r"ANNUAL|CONSUMPTION|الاستهلاك|سنويا|السنوي"
        )

        # Cooling capacity.
        kw_item = closest(capacity_anchor, kw_candidates)
        btu_item = closest(capacity_anchor, btu_candidates)

        if kw_item:
            cooling_kw = kw_item["value"]

        if btu_item:
            cooling_btu = btu_item["value"]

        # Fallback when the heading is missing or OCR did not detect it.
        if cooling_kw is None and kw_candidates:
            cooling_kw = kw_candidates[0]["value"]

        if cooling_btu is None and btu_candidates:
            cooling_btu = btu_candidates[0]["value"]

        # Metric value.
        if metric_evidence:
            metric_item = closest(
                metric_evidence,
                decimals,
                max_x=0.45,
                max_y=0.10
            )

            if metric_item:
                metric_value = metric_item["value"]

        if metric_value is None:
            remaining_decimals = [
                x for x in decimals
                if x["value"] != cooling_kw
                and 8.0 <= float(x["value"]) <= 30.0
            ]

            if remaining_decimals:
                metric_value = remaining_decimals[-1]["value"]

        # Annual consumption.
        annual_item = closest(
            annual_anchor,
            annual_candidates,
            max_x=0.55,
            max_y=0.16
        )

        if annual_item and annual_item["value"] != cooling_btu:
            annual_consumption = annual_item["value"]

        else:
            remaining_integers = [
                x for x in annual_candidates
                if x["value"] != cooling_btu
            ]

            if remaining_integers:
                annual_consumption = remaining_integers[-1]["value"]

    # --------------------------------------------------
    # 6. Efficiency rating
    # --------------------------------------------------

    # Rating detection remains separate.
    rating = None
    rating_evidence = None

    # --------------------------------------------------
    # 7. Registration and standard
    # --------------------------------------------------

    registration_number = None
    standard_reference = None

    for item in prepared:
        text = item["text"].strip()

        if re.search(r"\bE\d{3,}/\d{4}\b", text, re.I):
            registration_number = text

        if re.search(
            r"SASO|AS0|ASO|2663[/ -]2021|2863[/ -]2021",
            text,
            re.I
        ):
            standard_reference = text

    # --------------------------------------------------
    # 8. Confidence and review
    # --------------------------------------------------

    confidences = [
        x["confidence"]
        for x in prepared
        if x["confidence"] > 0
    ]

    average_confidence = (
        round(sum(confidences) / len(confidences), 3)
        if confidences else None
    )

    field_evidence = {
        "efficiency_metric": (
            metric_evidence["text"] if metric_evidence else None
        ),
        "annual_consumption": annual_consumption,
        "efficiency_rating": None
    }

    needs_review = (
        not prepared
        or average_confidence is None
        or average_confidence < MIN_LINE_CONFIDENCE
        or appliance_type is None
        or brand is None
        or model_number is None
        or rating is None
    )

    description_parts = []

    if appliance_type:
        description_parts.append(
            f"The label appears to be for an {appliance_type.lower()}."
        )

    if brand:
        description_parts.append(f"Detected brand: {brand}.")

    if model_number:
        description_parts.append(
            f"Possible model number: {model_number}."
        )

    if metric and metric_value:
        description_parts.append(
            f"Possible {metric} value: {metric_value}."
        )

    if annual_consumption:
        description_parts.append(
            f"Possible annual energy consumption: {annual_consumption} kWh."
        )

    if not description_parts:
        description_parts.append(
            "The system could not confidently identify the appliance details."
        )

    assigned = {
        cooling_kw,
        cooling_btu,
        metric_value,
        annual_consumption
    }

    unassigned = [
        x["value"]
        for x in numeric_lines
        if x["value"] not in assigned
    ]

    return {
        "appliance_type": appliance_type,
        "brand": brand,
        "model_number": model_number,
        "efficiency_rating_candidate": rating,
        "efficiency_metric": metric,
        "efficiency_metric_value_candidate": metric_value,
        "annual_energy_consumption_kwh": annual_consumption,
        "cooling_capacity_kw": cooling_kw,
        "cooling_capacity_btu_h": cooling_btu,
        "registration_number_candidate": registration_number,
        "standard_reference_candidate": standard_reference,
        "unassigned_numeric_candidates": unassigned,
        "field_evidence": field_evidence,
        "description": " ".join(description_parts),
        "needs_user_review": needs_review,
        "average_ocr_confidence": average_confidence,
        "raw_text": raw_text,
    }

def find_arrow_candidates(image):
    """Find colored shapes that may be standalone efficiency arrows."""

    if image is None or image.size == 0:
        return []

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    height, width = image.shape[:2]

    candidates = []

    kernel = np.ones((5, 5), np.uint8)

    for threshold in [60, 90, 120, 150]:

        mask = cv2.inRange(
            hsv,
            np.array([0, threshold, 40]),
            np.array([179, 255, 255])
        )

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            kernel
        )

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        for contour in contours:

            x, y, w, h = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)

            if area < 500:
                continue

            if w < 25 or h < 15:
                continue

            aspect = w / max(h, 1)

            if not 1.3 <= aspect <= 3.0:
                continue

            if w > width * 0.30 or h > height * 0.20:
                continue

            if x <= 1 or y <= 1:
                continue

            candidates.append({
                "box": (x, y, w, h),
                "area": area,
                "aspect": aspect
            })

    # Remove duplicate detections.
    unique = []

    for candidate in candidates:

        x, y, w, h = candidate["box"]
        duplicate = False

        for existing in unique:

            ex, ey, ew, eh = existing["box"]

            overlap_x = max(
                0, min(x + w, ex + ew) - max(x, ex)
            )

            overlap_y = max(
                0, min(y + h, ey + eh) - max(y, ey)
            )

            overlap = overlap_x * overlap_y
            smaller_area = min(w * h, ew * eh)

            if smaller_area > 0 and overlap / smaller_area > 0.65:
                duplicate = True
                break

        if not duplicate:
            unique.append(candidate)

    return unique

def select_arrow(candidates, image_width):
    """
    Select the candidate closest to the left edge.
    """

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda candidate: candidate["box"][0] / image_width
    )



def enlarge_arrow_crop(image, box):
    """Crop and enlarge the selected efficiency arrow."""

    x, y, w, h = box
    height, width = image.shape[:2]

    padding_x = int(w * 0.30)
    padding_y = int(h * 0.35)

    x1 = max(0, x - padding_x)
    y1 = max(0, y - padding_y)

    x2 = min(width, x + w + padding_x)
    y2 = min(height, y + h + padding_y)

    crop = image[y1:y2, x1:x2]

    if crop.size == 0:
        raise ValueError("The selected arrow crop is empty.")

    enlarged = cv2.resize(
        crop,
        None,
        fx=4,
        fy=4,
        interpolation=cv2.INTER_CUBIC
    )

    return enlarged



def detect_efficiency_rating(image_path):
    """Detect the efficiency grade using OCR with yellow-color assistance."""

    image = cv2.imread(str(image_path))

    if image is None:
        return {
            "rating": None,
            "confidence": 0.0,
            "method": "failed",
            "candidates": [],
            "selected_box": None
        }

    candidates = find_arrow_candidates(image)
    candidate_boxes = [c["box"] for c in candidates]

    selected = select_arrow(candidates, image.shape[1])

    if selected is None:
        return {
            "rating": None,
            "confidence": 0.0,
            "method": "no_candidate",
            "candidates": candidate_boxes,
            "selected_box": None
        }

    x, y, w, h = selected["box"]
    print(f"Selected candidate: {selected['box']}")

    # Check yellow color in the original candidate region.
    region = image[y:y+h, x:x+w]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

    yellow_mask = cv2.inRange(
        hsv,
        np.array([18, 70, 70]),
        np.array([38, 255, 255])
    )

    yellow_ratio = np.count_nonzero(yellow_mask) / max(
        yellow_mask.size, 1
    )

    is_yellow = yellow_ratio >= 0.15

    # Create the enlarged crop for OCR.
    crop = enlarge_arrow_crop(image, selected["box"])

    crop_path = (
        Path(image_path).parent / "rating_arrow_crop.jpg"
    )

    if not cv2.imwrite(str(crop_path), crop):
        raise ValueError("Could not save the arrow crop.")

    engine = get_ocr_engine()
    result = engine.predict(input=str(crop_path))
    lines = flatten_paddle_result(result)

    grade_mapping = {
        "A": "أ",
        "B": "ب",
        "C": "ج",
        "D": "د",
        "E": "هـ",
        "F": "و",
        "G": "ز"
    }

    allowed_arabic = {"أ", "ب", "ج", "د", "هـ", "و", "ز"}
    matches = []

    for line in lines:
        recognized_text = normalize_text(
            line.get("text", "")
        ).strip()

        if recognized_text in allowed_arabic:
            grade = recognized_text
        elif recognized_text.upper() in grade_mapping:
            grade = grade_mapping[recognized_text.upper()]
        else:
            continue

        try:
            confidence = float(line.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        matches.append({
            "rating": grade,
            "confidence": confidence
        })

    unique_grades = {m["rating"] for m in matches}

    ocr_grade = None
    ocr_confidence = 0.0

    if len(unique_grades) == 1:
        ocr_grade = unique_grades.pop()
        ocr_confidence = max(
            m["confidence"] for m in matches
            if m["rating"] == ocr_grade
        )

    # Combine OCR with color evidence.
    if ocr_grade == "د" and is_yellow:
        final_grade = "د"
        method = "ocr_and_color"

    elif ocr_grade is not None:
        final_grade = ocr_grade
        method = "ocr"

    elif is_yellow:
        final_grade = "د"
        method = "color_inferred"

    else:
        final_grade = None
        method = "unrecognized"

    return {
        "rating": final_grade,
        "confidence": ocr_confidence,
        "method": method,
        "yellow_ratio": round(float(yellow_ratio), 3),
        "candidates": candidate_boxes,
        "selected_box": selected["box"]
    }


def order_points(points):
    points = np.array(points, dtype="float32")
    ordered = np.zeros((4, 2), dtype="float32")

    s = points.sum(axis=1)
    diff = np.diff(points, axis=1)

    ordered[0] = points[np.argmin(s)]       # top-left
    ordered[2] = points[np.argmax(s)]       # bottom-right
    ordered[1] = points[np.argmin(diff)]    # top-right
    ordered[3] = points[np.argmax(diff)]   # bottom-left

    return ordered



def correct_perspective(image):
    """
    Detect and straighten the outer energy-label boundary.
    Returns the original image if a reliable boundary is not found.
    """

    if image is None or image.size == 0:
        return image

    height, width = image.shape[:2]
    image_area = height * width

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    # Detect label boundaries
    edges = cv2.Canny(gray, 40, 130)

    kernel = np.ones((5, 5), np.uint8)
    edges = cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, kernel, iterations=2
    )

    contours, _ = cv2.findContours(
        edges,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    contours = sorted(
        contours,
        key=cv2.contourArea,
        reverse=True
    )

    best_corners = None
    best_score = -1

    # Try different approximation tolerances
    for contour in contours[:30]:

        area = cv2.contourArea(contour)

        if area < image_area * 0.08:
            continue

        for epsilon in (0.01, 0.015, 0.02, 0.025, 0.03, 0.04):

            perimeter = cv2.arcLength(contour, True)

            approx = cv2.approxPolyDP(
                contour,
                epsilon * perimeter,
                True
            )

            if len(approx) != 4 or not cv2.isContourConvex(approx):
                continue

            corners = order_points(
                approx.reshape(4, 2)
            )

            tl, tr, br, bl = corners

            top_width = np.linalg.norm(tr - tl)
            bottom_width = np.linalg.norm(br - bl)
            left_height = np.linalg.norm(bl - tl)
            right_height = np.linalg.norm(br - tr)

            new_width = int(max(top_width, bottom_width))
            new_height = int(max(left_height, right_height))

            if new_width < 150 or new_height < 250:
                continue

            # Energy labels are normally portrait-shaped.
            ratio = new_width / new_height

            if not 0.35 <= ratio <= 0.95:
                continue

            if area > image_area * 0.95:
                continue

            # Prefer large, portrait-shaped candidates.
            score = area / image_area

            if score > best_score:
                best_score = score
                best_corners = corners

    if best_corners is None:
        print("No reliable label boundary found. Keeping original image.")
        return image

    tl, tr, br, bl = best_corners

    new_width = int(max(
        np.linalg.norm(br - bl),
        np.linalg.norm(tr - tl)
    ))

    new_height = int(max(
        np.linalg.norm(tr - br),
        np.linalg.norm(tl - bl)
    ))

    destination = np.array([
        [0, 0],
        [new_width - 1, 0],
        [new_width - 1, new_height - 1],
        [0, new_height - 1]
    ], dtype="float32")

    matrix = cv2.getPerspectiveTransform(
        best_corners,
        destination
    )

    corrected = cv2.warpPerspective(
        image,
        matrix,
        (new_width, new_height)
    )

    print("Energy label perspective correction applied.")

    return corrected

def enhance_for_ocr(image):
    """Enhance small printed text for OCR recognition."""

    # 1. Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 2. Improve local contrast
    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8)
    )
    contrast = clahe.apply(gray)

    # 3. Reduce noise while preserving text edges
    denoised = cv2.bilateralFilter(
        contrast, 7, 40, 40
    )

    # 4. Sharpen letters and numbers
    blurred = cv2.GaussianBlur(
        denoised, (0, 0), 1.0
    )
    sharpened = cv2.addWeighted(
        denoised, 1.4, blurred, -0.4, 0
    )

    # 5. Enlarge small text
    enlarged = cv2.resize(
        sharpened,
        None,
        fx=2.0,
        fy=2.0,
        interpolation=cv2.INTER_CUBIC
    )

    return enlarged

def preprocess_image(source: Path, destination: Path) -> None:
    """Apply EXIF orientation and convert to RGB for OCR."""
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        if image.width < 80 or image.height < 80:
            raise ValueError("Image is too small to read reliably.")
        image.convert("RGB").save(destination, format="JPEG", quality=95)

# ==========================================
# EcoWatt app entry point (added for the backend)
# ==========================================

MIN_SCAN_SIDE = 1100      # small images (e.g. web screenshots) are enlarged to this before scanning


def _enlarge_if_small(src: Path, dst: Path) -> Path:
    """Upscale images whose longest side is below MIN_SCAN_SIDE. On a 550 px SASO label this let the
    grade arrow and the cooling efficiency be read (they were missed at the original size)."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        longest = max(im.size)
        if longest >= MIN_SCAN_SIDE:
            return src
        scale = MIN_SCAN_SIDE / longest
        im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS).save(dst)
    return dst


ARABIC_TO_LATIN_GRADE = {"أ": "A", "ب": "B", "ج": "C", "د": "D", "هـ": "E", "و": "F", "ز": "G"}


def _number(value):
    """'18,600' / '5.46' / 6049 -> float, or None."""
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


# ------------------------------------------------------------
# Appliance analysis: notebook cell "generate_appliance_analysis", same wording and rules,
# returned as sections for the app instead of a Markdown report.
# ------------------------------------------------------------
GRADE_EXPLANATIONS_AC = {
    "A": "This AC has the highest efficiency level on the label.",
    "B": "This AC has a high efficiency level, just below A.",
    "C": "This AC is less efficient than models rated A or B.",
    "D": "This AC is less energy-efficient than models rated A, B, or C.",
    "E": "This AC is less energy-efficient than models rated A, B, C, or D.",
    "F": "This AC has a low efficiency rating compared with higher-rated models.",
    "G": "This AC has the lowest efficiency level on the label.",
}
ANNUAL_KWH_EXPLANATION = (
    "This represents the estimated annual electricity consumption under the label's specified testing "
    "conditions. Actual consumption may vary depending on usage and operating conditions."
)
COOLING_CAPACITY_EXPLANATION = "This indicates how much cooling the AC can provide."


def appliance_analysis(appliance_type, grade, annual_kwh, cooling_btu) -> dict:
    """The notebook's analysis for one scanned label (grade meaning, value explanations, tip)."""
    appliance_type = appliance_type or "Not detected"
    is_ac = str(appliance_type).strip().lower() in ["air conditioner", "ac"]

    if is_ac and grade:
        summary = GRADE_EXPLANATIONS_AC.get(grade, "The efficiency grade could not be determined reliably.")
    elif grade:
        summary = (f"The extracted efficiency grade is {grade}, but its interpretation requires confirming the "
                   "appliance type and applicable labeling standard.")
    else:
        summary = "The efficiency grade could not be determined reliably."

    has_grade, has_kwh, has_capacity = bool(grade), annual_kwh is not None, cooling_btu is not None
    recommendation = None
    if is_ac:
        if has_grade and has_kwh and has_capacity:
            recommendation = ("Consider the AC's efficiency grade and annual electricity consumption when choosing a "
                              "model. Make sure its cooling capacity meets your cooling needs.")
        elif has_grade and has_capacity:
            recommendation = ("Consider the AC's efficiency grade when choosing a model. "
                              "Make sure its cooling capacity meets your cooling needs.")
        elif has_grade and has_kwh:
            recommendation = ("Consider the AC's efficiency grade and annual electricity consumption when choosing "
                              "a model.")
        elif has_grade:
            recommendation = ("Consider the AC's efficiency grade when choosing a model. "
                              "Review its specifications before purchasing.")
        elif has_capacity:
            recommendation = ("Make sure the AC's cooling capacity meets your cooling needs. "
                              "Check its energy efficiency grade before purchasing.")
        else:
            recommendation = "Review the AC's energy label and specifications before purchasing."

    return {
        "appliance": appliance_type,
        "grade_meaning": summary,
        "annual_kwh_explanation": ANNUAL_KWH_EXPLANATION if has_kwh else None,
        "cooling_capacity_explanation": COOLING_CAPACITY_EXPLANATION if has_capacity else None,
        "tip": recommendation,
    }


def analyze_label(image_path) -> dict:
    """Scan one AC energy-label image. Returns the fields for the app (nothing is saved)."""
    image_path = Path(image_path)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        prepared = tmp / "prepared.jpg"
        enhanced = tmp / "enhanced.jpg"

        preprocess_image(_enlarge_if_small(image_path, tmp / "enlarged.png"), prepared)
        image = cv2.imread(str(prepared))
        if image is None:
            raise ValueError("Could not read the uploaded image.")
        if not cv2.imwrite(str(enhanced), enhance_for_ocr(image)):
            raise ValueError("Could not prepare the image for OCR.")

        try:
            rating = detect_efficiency_rating(prepared)          # grade comes only from the arrow detector
        except Exception:
            rating = {"rating": None, "confidence": 0.0, "method": "failed"}

        lines = flatten_paddle_result(get_ocr_engine().predict(input=str(enhanced)))
        fields = extract_fields(lines)

    grade_ar = rating.get("rating")
    annual = _number(fields.get("annual_energy_consumption_kwh"))
    found = {
        "grade": grade_ar is not None,
        "cooling_capacity": bool(fields.get("cooling_capacity_btu_h") or fields.get("cooling_capacity_kw")),
        "efficiency": bool(fields.get("efficiency_metric_value_candidate")),
        "annual_kwh": annual is not None,
    }
    if not any(found.values()) and not lines:
        return {"success": False,
                "message": "We couldn't read an energy label in this photo. Try a clear, straight photo of the label."}

    appliance = fields.get("appliance_type") or "Air conditioner"     # the scanner only supports AC labels
    grade = ARABIC_TO_LATIN_GRADE.get(grade_ar)
    btu = _number(fields.get("cooling_capacity_btu_h"))
    return {
        "success": True,
        "analysis": appliance_analysis(appliance, grade, annual, btu),
        "appliance_type": appliance,
        "brand": fields.get("brand"),
        "model_number": fields.get("model_number"),
        "grade": grade,
        "grade_arabic": grade_ar,
        "cooling_capacity_btu_h": btu,
        "cooling_capacity_kw": _number(fields.get("cooling_capacity_kw")),
        "efficiency_metric": fields.get("efficiency_metric"),
        "efficiency_value": _number(fields.get("efficiency_metric_value_candidate")),
        "annual_kwh": annual,
        "found": found,
        "complete": all(found.values()),
        "message": ("Label read successfully. Please check the values against your label."
                    if all(found.values()) else
                    "Some values could not be read. Please check them against your label."),
    }
