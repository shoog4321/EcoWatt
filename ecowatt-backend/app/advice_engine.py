"""Component B: catalog-constrained advice generation (report 4.6.3.4 + section 7).

Pipeline for ONE bill:
  context -> constrained LLM call -> validate -> bounded repair -> safety layer -> first-name prefix

Dependency-free on purpose (stdlib only): the LLM is injected, so this module is
unit-testable without a GPU.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .safety import SafetyRules

log = logging.getLogger("ecowatt.advice")

MIN_ITEMS, MAX_ITEMS, MAX_CHARS = 3, 6, 380


class ChatClient(Protocol):
    async def complete_json(self, messages: list[dict], schema: dict, max_tokens: int = 640) -> str: ...


class AdviceGenerationError(RuntimeError):
    """The model could not produce a valid advice list (not an availability problem)."""


# ----------------------------------------------------------------------------- catalog
@dataclass(frozen=True)
class CatalogItem:
    advice_id: str
    type: str
    title: str
    advice: str
    applicability: str = "all"      # "all" | "winter"
    requires_purchase: bool = False  # buying something (LED bulbs, smart thermostat, ...)


def applies_in(item: CatalogItem, season: str | None) -> bool:
    """Winter-only catalog items (heating tips) must not reach a non-winter bill."""
    if item.applicability.strip().lower() != "winter":
        return True
    return str(season or "").strip().lower() == "winter"


def excluded_ids(catalog: dict[str, CatalogItem], *, season: str | None, willing_to_upgrade: str | None,
                 applied: set[str] | frozenset[str] = frozenset()) -> frozenset[str]:
    """Catalog items the model must not pick for this household and bill:
      * winter-only items outside winter
      * purchase items when the household answered No to upgrading appliances
      * items the household already marked as applied on earlier bills
    Applied items are only excluded while enough other items remain (catalog exhausted -> repeats allowed)."""
    hard = {a for a, i in catalog.items() if not applies_in(i, season)}
    if str(willing_to_upgrade or "").strip().lower() == "no":
        hard |= {a for a, i in catalog.items() if i.requires_purchase}
    soft = {a for a in applied if a in catalog} - hard
    if len(catalog) - len(hard) - len(soft) < MAX_ITEMS:
        soft = set()
    return frozenset(hard | soft)


def load_catalog(path: Path) -> dict[str, CatalogItem]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("advice") or list(rows.values())
    catalog: dict[str, CatalogItem] = {}
    for row in rows:
        r = {str(k).strip().lower().replace(" ", "_"): v for k, v in row.items()}
        aid = r.get("advice_id") or r.get("id")
        # hand-off catalog (report 12.1) uses approved_advice / approved_type
        text = r.get("advice") or r.get("approved_advice") or r.get("processed_advice")
        ctype = r.get("type") or r.get("approved_type") or ""
        if not aid or not text:
            raise ValueError(f"Catalog row missing advice_id/advice: {row}")
        catalog[str(aid)] = CatalogItem(str(aid), str(ctype), str(r.get("title", "")), str(text),
                                        str(r.get("applicability") or "all"),
                                        bool(r.get("requires_purchase", False)))
    return catalog


# ----------------------------------------------------------------------------- prompt context
def build_payload(case_id: str, profile: dict, period: dict, analysis: dict,
                  catalog: dict[str, CatalogItem]) -> dict:
    """What the model sees (report 4.6.3.4 example payload). The evidence rules and
    output format live in the system prompt. Profile must NOT contain names/IDs."""
    # The evaluation seeded its shuffle from MD5(case_id). Swap in the notebook's exact
    # routine if you need byte-identical orderings; any stable shuffle works functionally.
    seed = int(hashlib.md5(case_id.encode()).hexdigest(), 16)
    items = [i for i in catalog.values() if applies_in(i, period.get("season"))]
    random.Random(seed).shuffle(items)
    return {
        "household_profile": profile,
        "period": period,
        "analysis": analysis,
        "candidates": [{"advice_id": i.advice_id, "type": i.type, "advice": i.advice} for i in items],
        "min_advice": MIN_ITEMS,
        "max_advice": MAX_ITEMS,
    }


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def advice_schema(ids: list[str], lo: int, hi: int) -> dict:
    lo = min(lo, len(ids))
    return {
        "type": "object",
        "properties": {
            "advice": {
                "type": "array",
                "minItems": lo,
                "maxItems": min(hi, len(ids)),
                "items": {
                    "type": "object",
                    "properties": {
                        "advice_id": {"type": "string", "enum": ids},
                        "personalized_advice": {"type": "string", "minLength": 1, "maxLength": MAX_CHARS},
                    },
                    "required": ["advice_id", "personalized_advice"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["advice"],
        "additionalProperties": False,
    }


# ----------------------------------------------------------------------------- validation
def parse_items(raw: str) -> tuple[list[dict], list[str]]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        return [], [f"Output is not valid JSON ({e})."]
    arr = data.get("advice") if isinstance(data, dict) else None
    if not isinstance(arr, list):
        return [], ["Top-level object must contain an 'advice' array."]
    items, errors = [], []
    for i, it in enumerate(arr):
        if not isinstance(it, dict) or set(it) != {"advice_id", "personalized_advice"}:
            errors.append(f"Item {i} must have exactly advice_id and personalized_advice.")
            continue
        items.append({"advice_id": str(it["advice_id"]), "personalized_advice": str(it["personalized_advice"]).strip()})
    return items, errors


def _leaks_name(text: str, names: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(n)}\b", text, re.IGNORECASE) for n in names)


def check_items(items: list[dict], catalog: dict[str, CatalogItem], names: list[str],
                already: frozenset[str] = frozenset(), season: str | None = None,
                exclude: frozenset[str] = frozenset()) -> tuple[list[dict], list[str]]:
    clean, errors, seen = [], [], set(already)
    for it in items:
        aid, text = it["advice_id"], it["personalized_advice"]
        if aid not in catalog:
            errors.append(f"{aid} is not in the approved catalog.")
        elif aid in exclude:
            errors.append(f"{aid} is excluded for this household (applied before, purchase or off-season).")
        elif season is not None and not applies_in(catalog[aid], season):
            errors.append(f"{aid} is winter-only advice but the bill is for {season}.")
        elif aid in seen:
            errors.append(f"{aid} is duplicated.")
        elif not text or len(text) > MAX_CHARS:
            errors.append(f"{aid}: text is empty or longer than {MAX_CHARS} characters.")
        elif _leaks_name(text, names):
            errors.append(f"{aid}: text contains a personal name.")
        else:
            seen.add(aid)
            clean.append({"advice_id": aid, "personalized_advice": text})
    return clean, errors


# ----------------------------------------------------------------------------- engine
@dataclass
class GenerationResult:
    items: list[dict]   # advice_id, personalized_advice, title, type
    audit: list[dict]   # per-item safety outcome: ok | repaired | prefixed | unresolved


class AdviceEngine:
    def __init__(self, llm: ChatClient, catalog: dict[str, CatalogItem], system_prompt: str,
                 safety: SafetyRules):
        self.llm, self.catalog, self.system_prompt, self.safety = llm, catalog, system_prompt, safety

    async def generate(self, *, case_id: str, profile: dict, period: dict, analysis: dict,
                       first_name: str = "", last_name: str = "",
                       exclude_ids: frozenset[str] = frozenset()) -> GenerationResult:
        if exclude_ids:          # run on a copy of the engine that only knows the allowed items
            allowed = {k: v for k, v in self.catalog.items() if k not in exclude_ids}
            return await AdviceEngine(self.llm, allowed, self.system_prompt, self.safety).generate(
                case_id=case_id, profile=profile, period=period, analysis=analysis,
                first_name=first_name, last_name=last_name)
        names = [n for n in (first_name, last_name) if n and len(n) > 1]
        payload = build_payload(case_id, profile, period, analysis, self.catalog)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": _dump(payload)},
        ]
        ids = list(self.catalog)

        # 1) full generation, schema-constrained
        raw = await self.llm.complete_json(messages, advice_schema(ids, MIN_ITEMS, MAX_ITEMS))
        items, errors = self._parse_check(raw, names)

        # 2) one list-level repair with the validation errors as feedback
        if errors or not MIN_ITEMS <= len(items) <= MAX_ITEMS:
            problems = errors or [f"Return between {MIN_ITEMS} and {MAX_ITEMS} distinct items."]
            retry = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Your answer failed validation: " + " ".join(problems)
                 + " Return corrected JSON only."},
            ]
            raw2 = await self.llm.complete_json(retry, advice_schema(ids, MIN_ITEMS, MAX_ITEMS))
            items2, _ = self._parse_check(raw2, names)
            items = max(items, items2, key=len)
        items = items[:MAX_ITEMS]

        # 3) top-up from unused IDs if fewer than 3 survived
        if len(items) < MIN_ITEMS:
            items = await self._top_up(messages, items, names)
        if len(items) < MIN_ITEMS:
            raise AdviceGenerationError(f"Only {len(items)} valid advice items after repair ({case_id}).")

        # 4) safety layer
        context = {k: v for k, v in payload.items() if k != "candidates"}
        items, audit = await self._enforce_safety(items, context)

        # Names are only used above to drop items that leak them; the advice text never includes the user's name.
        enriched = [
            {**it, "title": self.catalog[it["advice_id"]].title, "type": self.catalog[it["advice_id"]].type}
            for it in items
        ]
        return GenerationResult(enriched, audit)

    # ------------------------------------------------------------------ helpers
    def _parse_check(self, raw: str, names: list[str]) -> tuple[list[dict], list[str]]:
        items, errs = parse_items(raw)
        clean, errs2 = check_items(items, self.catalog, names)
        return clean, errs + errs2

    async def _top_up(self, messages: list[dict], items: list[dict], names: list[str]) -> list[dict]:
        used = frozenset(i["advice_id"] for i in items)
        unused = [i for i in self.catalog if i not in used]
        need, room = MIN_ITEMS - len(items), MAX_ITEMS - len(items)
        retry = messages + [
            {"role": "assistant", "content": _dump({"advice": items})},
            {"role": "user", "content": f"Select {need} to {room} more distinct items from the remaining "
                                         "approved IDs, following the same rules. Return JSON only."},
        ]
        raw = await self.llm.complete_json(retry, advice_schema(unused, need, room))
        extra, _ = parse_items(raw)
        extra, _ = check_items(extra, self.catalog, names, already=used)
        return items + extra

    async def _enforce_safety(self, items: list[dict], context: dict) -> tuple[list[dict], list[dict]]:
        out, audit = [], []
        for it in items:
            aid, text = it["advice_id"], it["personalized_advice"]
            missing = self.safety.missing(aid, text)
            if not missing:
                out.append(it)
                audit.append({"advice_id": aid, "safety": "ok"})
                continue
            log.info("safety miss %s: %s", aid, missing)
            status, final = "unresolved", text

            repaired = await self._repair_one(aid, text, context)
            if repaired and not self.safety.missing(aid, repaired):
                status, final = "repaired", repaired
            else:
                prefixed = self.safety.with_prefix(aid, text)
                if prefixed and not self.safety.missing(aid, prefixed):
                    status, final = "prefixed", prefixed
            if status == "unresolved":
                log.warning("safety condition NOT preserved for %s", aid)
            out.append({"advice_id": aid, "personalized_advice": final})
            audit.append({"advice_id": aid, "safety": status, "missing_patterns": missing})
        return out, audit

    async def _repair_one(self, aid: str, text: str, context: dict) -> str | None:
        request = {
            "task": "Rewrite this ONE advice sentence so it keeps its mandatory condition. "
                    "Return exactly one item with the same advice_id.",
            "advice_id": aid,
            "approved_advice": self.catalog[aid].advice,
            "previous_sentence": text,
            "must_keep": self.safety.hint(aid),
            "household_context": context,
        }
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": _dump(request)},
        ]
        try:
            raw = await self.llm.complete_json(messages, advice_schema([aid], 1, 1), max_tokens=220)
        except Exception:  # availability errors during repair must not discard a good list
            log.exception("single-item repair failed for %s", aid)
            return None
        items, _ = parse_items(raw)
        clean, _ = check_items(items, self.catalog, [])
        return clean[0]["personalized_advice"] if clean else None
