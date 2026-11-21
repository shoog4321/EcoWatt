import cv2
import torch
import easyocr
import re
import difflib
from collections import Counter


# ==========================================
# Initialize EasyOCR once
# ==========================================

gpu_available = torch.cuda.is_available()

reader = easyocr.Reader(
    ['ar', 'en'],
    gpu=gpu_available
)


# ==========================================
# Constants
# ==========================================

arabic_to_english = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩",
    "0123456789"
)

KWH_UNIT_VARIANTS = [
    "ك و س",
    "كوس",
    "ك.و.س",
    "كيلو وات",
    "kwh"
]

CURRENCY_VARIANTS = [
    "ريال",
    "ر.س",
    "﷼",
    "sar"
]

MAX_RAW_DIGITS = 7

AMOUNT_RANGE = (0.5, 100000)
CONSUMPTION_RANGE = (0.5, 100000)

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December"
]


# ==========================================
# Text normalization
# ==========================================

def normalize(text):

    text = text.translate(arabic_to_english)

    text = (
        text
        .replace("٫", ".")
        .replace("،", ",")
        .replace("٬", ",")
    )

    text = re.sub(
        r'[\u0617-\u061A\u064B-\u0652\u0640]',
        '',
        text
    )

    return text


# ==========================================
# OCR
# ==========================================

def extract_ocr_lines(image_path):

    image = cv2.imread(image_path)

    if image is None:
        raise ValueError(
            "Could not read the uploaded image."
        )

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    scale = (
        2.0
        if max(gray.shape[:2]) < 2000
        else 1.0
    )

    if scale != 1.0:
        gray = cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC
        )

    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8)
    )

    gray = clahe.apply(gray)

    ocr_image = cv2.cvtColor(
        gray,
        cv2.COLOR_GRAY2BGR
    )

    results = reader.readtext(
        ocr_image,
        detail=1,
        paragraph=False,
        width_ths=1.2,
        height_ths=0.6,
        y_ths=0.5
    )

    items = []

    for bbox, text, confidence in results:

        text = text.strip()

        if not text:
            continue

        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]

        items.append({
            "text": text,
            "confidence": confidence,
            "x": (
                min(xs) + max(xs)
            ) / 2,
            "y": (
                min(ys) + max(ys)
            ) / 2,
            "height":
                max(ys) - min(ys)
        })

    items.sort(
        key=lambda x: x["y"]
    )

    lines = []

    for item in items:

        placed = False

        for line in lines:

            avg_y = sum(
                x["y"]
                for x in line
            ) / len(line)

            avg_height = sum(
                x["height"]
                for x in line
            ) / len(line)

            if (
                abs(
                    item["y"] - avg_y
                )
                <= avg_height * 0.7
            ):

                line.append(item)
                placed = True
                break

        if not placed:
            lines.append([item])

    ocr_lines = []

    for line in lines:

        line.sort(
            key=lambda x: x["x"],
            reverse=True
        )

        ocr_lines.append(
            normalize(
                " ".join(
                    x["text"]
                    for x in line
                )
            )
        )

    return ocr_lines


# ==========================================
# Fuzzy Matching
# ==========================================

def fuzzy_ratio(a, b):

    return difflib.SequenceMatcher(
        None,
        a,
        b
    ).ratio()


def best_fuzzy_line(
    ocr_lines,
    target_variants,
    threshold=0.55
):

    best = (
        None,
        None,
        0.0
    )

    for i, line in enumerate(
        ocr_lines
    ):

        for kw in target_variants:

            klen = len(kw)

            for start in range(
                0,
                max(
                    1,
                    len(line)
                    - klen
                    + 3
                )
            ):

                window = line[
                    start:
                    start + klen + 3
                ]

                score = fuzzy_ratio(
                    window,
                    kw
                )

                if score > best[2]:

                    best = (
                        i,
                        kw,
                        score
                    )

    if best[2] >= threshold:
        return best

    return (
        None,
        None,
        0.0
    )


# ==========================================
# Number extraction
# ==========================================

def isolate_segment(
    text,
    start,
    max_len=40
):

    seg = text[
        start:
        start + max_len
    ]

    cut = re.search(
        r'[^\d\s.,:()\-]{2,}',
        seg
    )

    if cut:
        seg = seg[:cut.start()]

    return seg


def parse_numbers_from_segment(
    segment
):

    if not segment:
        return []

    segment = normalize(segment)

    tokens = re.findall(
        r'[\d.,]+',
        segment
    )

    if not tokens:
        return []

    candidates = set()

    def add_float(s):

        s = s.replace(
            ',',
            '.'
        )

        if s.count('.') > 1:

            parts = s.split('.')

            s = (
                "".join(parts[:-1])
                + "."
                + parts[-1]
            )

        if '.' in s:

            integer_part, decimal_part = (
                s.split('.')
            )

            if len(decimal_part) >= 3:

                s = (
                    integer_part
                    + decimal_part
                )

        s = s.strip('.,')

        if not s:
            return

        if (
            len(s)
            > MAX_RAW_DIGITS + 3
        ):
            return

        try:

            base_val = float(s)

            candidates.add(
                round(
                    base_val,
                    2
                )
            )

        except ValueError:
            return

        if (
            '.' not in s
            and base_val > 99
        ):

            if (
                len(s) >= 4
                and s[-3] == '0'
            ):

                fixed_s = (
                    s[:-3]
                    + '.'
                    + s[-2:]
                )

                try:
                    candidates.add(
                        round(
                            float(
                                fixed_s
                            ),
                            2
                        )
                    )

                except ValueError:
                    pass

            elif (
                len(s) >= 3
                and s[-2] == '0'
            ):

                fixed_s = (
                    s[:-2]
                    + '.'
                    + s[-1:]
                )

                try:
                    candidates.add(
                        round(
                            float(
                                fixed_s
                            ),
                            2
                        )
                    )

                except ValueError:
                    pass

            else:

                if base_val > 1000:

                    fixed_s = (
                        f"{s[:-2]}.{s[-2:]}"
                    )

                    try:
                        candidates.add(
                            round(
                                float(
                                    fixed_s
                                ),
                                2
                            )
                        )

                    except ValueError:
                        pass

    clean_tokens = [
        t
        for t in tokens
        if re.search(
            r'\d',
            t
        )
    ]

    if not clean_tokens:
        return []

    tokens_a = [
        '.'
        if t == '0'
        else t
        for t in clean_tokens
    ]

    add_float(
        "".join(
            reversed(tokens_a)
        )
    )

    add_float(
        "".join(
            reversed(clean_tokens)
        )
    )

    add_float(
        "".join(clean_tokens)
    )

    tokens_d = [
        t
        for t in tokens
        if t.strip()
    ]

    add_float(
        "".join(
            reversed(tokens_d)
        )
    )

    for t in tokens:

        if (
            len(t) >= 3
            and (
                '.' in t
                or ',' in t
            )
        ):

            add_float(t)

    return list(candidates)


def find_unit_anchored_number(
    ocr_lines,
    unit_variants,
    plausible_range
):

    candidates = []

    for line in ocr_lines:

        for uv in unit_variants:

            pos = line.lower().find(
                uv.lower()
            )

            if pos == -1:

                for start in range(
                    0,
                    max(
                        1,
                        len(line)
                        - len(uv)
                        + 1
                    )
                ):

                    if (
                        fuzzy_ratio(
                            line[
                                start:
                                start
                                + len(uv)
                            ],
                            uv
                        )
                        >= 0.8
                    ):

                        pos = start
                        break

            if pos == -1:
                continue

            before = isolate_segment(
                line[:pos][::-1],
                0,
                15
            )[::-1]

            after = isolate_segment(
                line,
                pos + len(uv),
                15
            )

            for seg in (
                before,
                after
            ):

                vals = (
                    parse_numbers_from_segment(
                        seg
                    )
                )

                candidates.extend(
                    [
                        v
                        for v in vals
                        if (
                            plausible_range[0]
                            <= v
                            <= plausible_range[1]
                        )
                    ]
                )

    return candidates


# ==========================================
# Field extraction
# ==========================================

def find_keyword_position(
    line,
    keyword_variants,
    threshold=0.72
):

    for kw in keyword_variants:

        found = line.find(kw)

        if found != -1:
            return (
                found
                + len(kw)
            )

    best = (
        None,
        0.0
    )

    for kw in keyword_variants:

        klen = len(kw)

        for start in range(
            0,
            max(
                1,
                len(line)
                - klen
                + 1
            )
        ):

            score = fuzzy_ratio(
                line[
                    start:
                    start + klen
                ],
                kw
            )

            if score > best[1]:

                best = (
                    start + klen,
                    score
                )

    if best[1] >= threshold:
        return best[0]

    return None


def _keyword_lines(
    ocr_lines,
    keyword_variants
):
    """Indexes of lines containing the keyword: the best fuzzy match first, then
    the other matching lines in page order (a label can appear more than once,
    e.g. as a chart heading without a value)."""

    best_idx, _, _ = best_fuzzy_line(
        ocr_lines,
        keyword_variants
    )

    order = [] if best_idx is None else [best_idx]

    for i, line in enumerate(ocr_lines):

        if (
            i != best_idx
            and find_keyword_position(
                line,
                keyword_variants
            ) is not None
        ):
            order.append(i)

    return order


def _values_on_line(
    ocr_lines,
    idx,
    keyword_variants
):

    line = ocr_lines[idx]

    pos = find_keyword_position(
        line,
        keyword_variants
    )

    if pos is None:
        return []

    segment = isolate_segment(
        line,
        pos,
        max_len=40
    )

    vals = set(
        parse_numbers_from_segment(
            segment
        )
    )

    # The number right after the label, on its own: when a misread unit lets
    # the segment run into the next field, joining all tokens produces a
    # number that is too long and gets rejected.
    first = re.search(
        r'\d[\d.,]*',
        normalize(segment)
    )

    if first:
        vals.update(
            parse_numbers_from_segment(
                first.group()
            )
        )

    if (
        not vals
        and idx + 1
        < len(ocr_lines)
    ):

        next_line = (
            ocr_lines[idx + 1]
        )

        chunks = re.findall(
            r'(?:[\d]+[\s.,]*)+[\d]+',
            next_line
        )

        if chunks:

            vals = set(
                parse_numbers_from_segment(
                    chunks[-1]
                )
            )

    return list(vals)


def extract_value_after_keyword(
    ocr_lines,
    keyword_variants,
    plausible_range
):

    for idx in _keyword_lines(
        ocr_lines,
        keyword_variants
    ):

        vals = [
            v
            for v in _values_on_line(
                ocr_lines,
                idx,
                keyword_variants
            )
            if (
                plausible_range[0]
                <= v
                <= plausible_range[1]
            )
        ]

        if vals:
            return vals

    return []


def meter_reading_difference(
    ocr_lines,
    plausible_range
):
    """Consumption = end-of-period meter reading - start-of-period reading.
    Only readings parsed with two decimals are used (meter readings are printed
    that way), which keeps accidental combinations out."""

    readings = (0.5, 10 ** 7)

    starts = extract_value_after_keyword(
        ocr_lines,
        [
            "قراءة بداية الفترة",
            "قراءه بدايه الفتره"
        ],
        readings
    )

    ends = extract_value_after_keyword(
        ocr_lines,
        [
            "قراءة نهاية الفترة",
            "قراءه نهايه الفتره"
        ],
        readings
    )

    def has_decimals(v):
        return round(v * 100) % 100 != 0

    diffs = set()

    for a in starts:
        for b in ends:
            d = round(b - a, 2)
            if (
                has_decimals(a)
                and has_decimals(b)
                and plausible_range[0]
                <= d
                <= plausible_range[1]
            ):
                diffs.add(d)

    return list(diffs)


# ==========================================
# Consensus
# ==========================================

def consensus(
    weighted_values,
    rel_tol=0.03
):

    valid = [
        (v, w)
        for v, w
        in weighted_values
        if (
            v is not None
            and v > 0
        )
    ]

    if not valid:
        return None

    scores = Counter()

    for v, w in valid:

        for other_v, other_w in valid:

            if v == other_v:

                scores[
                    round(v, 2)
                ] += w

            elif (
                abs(v - other_v)
                <= max(
                    v,
                    other_v
                ) * rel_tol
            ):

                scores[
                    round(v, 2)
                ] += (
                    w * 0.5
                )

    return (
        scores
        .most_common(1)[0][0]
    )


# ==========================================
# Saudi electricity bill verification
# ==========================================

def calculate_expected_bill(
    consumption,
    meter_fee
):

    if consumption <= 6000:

        val = (
            consumption
            * 0.18
        )

    else:

        val = (
            6000 * 0.18
        ) + (
            (
                consumption
                - 6000
            )
            * 0.30
        )

    return (
        val + meter_fee
    ) * 1.15


def strict_double_check(
    primary_amounts,
    amount_cands,
    cons_cands
):

    best_match = None

    min_error = float(
        'inf'
    )

    primary_set = set(
        primary_amounts
    )

    c_set = set(
        c
        for c, w
        in cons_cands
        if (
            c is not None
            and c > 0
        )
    )

    for a in primary_set:

        for c in c_set:

            for fee in [
                10.0,
                15.0,
                21.0,
                30.0
            ]:

                expected_a = (
                    calculate_expected_bill(
                        c,
                        fee
                    )
                )

                error = (
                    abs(
                        a - expected_a
                    )
                    / max(a, 1)
                )

                if error < min_error:

                    min_error = error

                    best_match = (
                        a,
                        c
                    )

    if (
        best_match
        and min_error <= 0.05
    ):

        return (
            best_match,
            min_error,
            "Verified via Primary Field & Tariff Match"
        )

    return (
        None,
        min_error,
        "Failed strict check, fallback to weighted consensus"
    )


# ==========================================
# Date extraction
# ==========================================

def parse_date_segment(
    segment
):

    tokens = re.findall(
        r'\d+',
        normalize(segment)
    )

    if not tokens:
        return None

    str_reversed = "".join(
        reversed(tokens)
    )

    str_normal = "".join(
        tokens
    )

    for candidate in (
        str_reversed,
        str_normal
    ):

        year_match = re.search(
            r'(20[1-3][0-9])',
            candidate
        )

        if not year_match:
            continue

        y = year_match.group(1)

        rem = candidate.replace(
            y,
            "",
            1
        )

        parts = [
            int(p)
            for p in re.split(
                r'0+',
                rem
            )
            if p
        ]

        p1 = None
        p2 = None

        if len(parts) >= 2:

            p1 = parts[0]
            p2 = parts[1]

        elif len(parts) == 1:

            s = str(parts[0])

            if len(s) == 4:

                p1 = int(s[:2])
                p2 = int(s[2:])

            elif len(s) == 3:

                if int(s[:2]) <= 31:

                    p1 = int(s[:2])
                    p2 = int(s[2:])

                else:

                    p1 = int(s[:1])
                    p2 = int(s[1:])

        if (
            p1 is None
            or p2 is None
        ):
            continue

        m = None

        if (
            p1 > 12
            and p2 <= 12
        ):

            m = p2

        elif (
            p2 > 12
            and p1 <= 12
        ):

            m = p1

        elif (
            p1 <= 12
            and p2 <= 12
        ):

            m = (
                p1
                if candidate.startswith(y)
                else p2
            )

        if (
            m
            and 1 <= m <= 12
        ):

            return (
                f"{MONTHS[m - 1]} {y}"
            )

    return None


# ==========================================
# MAIN FUNCTION USED BY API
# ==========================================

def analyze_bill(image_path):

    # ---------- OCR ----------

    ocr_lines = (
        extract_ocr_lines(
            image_path
        )
    )

    if not ocr_lines:

        return {
            "success": False,
            "message":
                "No readable text was detected in the image.",
            "month": None,
            "amount_due": None,
            "consumption": None
        }

    # ---------- Amount ----------

    primary_amount_candidates = (
        extract_value_after_keyword(
            ocr_lines,
            [
                "المبلغ المطلوب سداده",
                "المبلغ المطلوب سدادة"
            ],
            AMOUNT_RANGE
        )
    )

    amount_candidates = []

    for v in primary_amount_candidates:

        amount_candidates.append(
            (v, 4.0)
        )

    for kws in [
        [
            "المبلغ شامل الضريبة",
            "المبلغ شامل الصربه",
            "المبلغ شامل الصريبه"
        ],
        [
            "إجمالي الفاتورة",
            "إجمالى الفاتورة",
            "اجمالي الفاتوره"
        ]
    ]:

        for v in (
            extract_value_after_keyword(
                ocr_lines,
                kws,
                AMOUNT_RANGE
            )
        ):

            amount_candidates.append(
                (v, 1.0)
            )

    for v in (
        find_unit_anchored_number(
            ocr_lines,
            CURRENCY_VARIANTS,
            AMOUNT_RANGE
        )
    ):

        amount_candidates.append(
            (v, 1.0)
        )

    # ---------- Consumption ----------

    consumption_candidates = []

    for v in (
        extract_value_after_keyword(
            ocr_lines,
            [
                "إجمالي الاستهلاك",
                "إجمالى الاستهلاك"
            ],
            CONSUMPTION_RANGE
        )
    ):

        consumption_candidates.append(
            (v, 3.0)
        )

    for v in (
        extract_value_after_keyword(
            ocr_lines,
            [
                "كمية الاستهلاك",
                "كمبه الاستهلاك"
            ],
            CONSUMPTION_RANGE
        )
    ):

        consumption_candidates.append(
            (v, 1.0)
        )

    for v in (
        find_unit_anchored_number(
            ocr_lines,
            KWH_UNIT_VARIANTS,
            CONSUMPTION_RANGE
        )
    ):

        consumption_candidates.append(
            (v, 1.0)
        )

    for v in (
        meter_reading_difference(
            ocr_lines,
            CONSUMPTION_RANGE
        )
    ):

        consumption_candidates.append(
            (v, 2.0)
        )

    flat_amount_cands = list(
        set(
            v
            for v, w
            in amount_candidates
        )
    )

    flat_cons_cands = list(
        set(
            v
            for v, w
            in consumption_candidates
        )
    )

    # ---------- Verification ----------

    (
        double_check_result,
        err_margin,
        check_status
    ) = strict_double_check(
        primary_amount_candidates,
        amount_candidates,
        consumption_candidates
    )

    if double_check_result:

        amount_due, consumption_value = (
            double_check_result
        )

        verified = True

    else:

        amount_due = consensus(
            amount_candidates
        )

        consumption_value = consensus(
            consumption_candidates
        )

        verified = False

    # ---------- Date ----------

    invoice_month = None

    DATE_KEYWORDS = [
        [
            "تاريخ الفاتورة",
            "تاريخ الفاتوره"
        ],
        [
            "بداية الاستحقاق"
        ],
        [
            "نهاية الفترة",
            "نهاية الفترذ"
        ],
        [
            "بداية الفترة"
        ]
    ]

    for kws in DATE_KEYWORDS:

        if invoice_month:
            break

        idx, _, _ = (
            best_fuzzy_line(
                ocr_lines,
                kws
            )
        )

        if idx is None:
            continue

        line = ocr_lines[idx]

        pos = find_keyword_position(
            line,
            kws
        )

        if pos is None:
            continue

        segment = isolate_segment(
            line,
            pos,
            max_len=25
        )

        invoice_month = (
            parse_date_segment(
                segment
            )
        )

    # ==========================================
    # Determine result status
    # ==========================================

    detected_count = sum([
        invoice_month is not None,
        amount_due is not None,
        consumption_value is not None
    ])

    if detected_count == 0:

        return {
            "success": False,

            "message":
                "We couldn't recognize the electricity bill. Please upload a clear bill image.",

            "month": None,
            "amount_due": None,
            "consumption": None,

            "verified": False
        }

    if detected_count < 3:

        message = (
            "Some information could not be detected. "
            "Please review and complete the missing fields."
        )

        status = "partial"

    else:

        message = (
            "Bill information extracted successfully. "
            "Please review the information before confirming."
        )

        status = "complete"

    # ==========================================
    # Final result
    # ==========================================

    return {
        "success": True,

        "status": status,

        "message": message,

        "month": invoice_month,

        "amount_due": amount_due,

        "consumption": consumption_value,

        "verified": verified,

        "verification_status":
            check_status,

        "error_margin":
            None
            if err_margin == float('inf')
            else err_margin,

        "amount_candidates":
            flat_amount_cands,

        "consumption_candidates":
            flat_cons_cands
    }