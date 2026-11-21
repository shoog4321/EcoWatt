"""Deterministic safety-condition enforcement (evaluation report, sections 7.4-7.5).

Some catalog items carry a mandatory condition ("when buying or replacing", ...).
Qwen tends to paraphrase these away, so every rendered item is checked against
intent-level regexes; failures get one targeted repair and, as a last resort, a
curated prefix. If nothing works the original item is kept (never a worse result).
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def lower_first(text: str) -> str:
    """Lower-case the first letter unless it starts an acronym ("AC", "LED")."""
    if len(text) > 1 and text[0].isupper() and text[1].islower():
        return text[0].lower() + text[1:]
    return text


class SafetyRules:
    def __init__(self, rules: dict[str, dict], prefixes: dict[str, str]):
        self._sources = {k: list(v["patterns"]) for k, v in rules.items()}
        self._compiled = {
            k: [re.compile(p, re.IGNORECASE) for p in v["patterns"]] for k, v in rules.items()
        }
        self._hints = {k: v.get("hint", "") for k, v in rules.items()}
        self._prefixes = dict(prefixes)

    @classmethod
    def load(cls, data_dir: Path) -> "SafetyRules":
        rules = json.loads((data_dir / "safety_rules.json").read_text(encoding="utf-8"))
        prefixes = json.loads((data_dir / "required_prefixes.json").read_text(encoding="utf-8"))
        return cls(rules, prefixes)

    def has_rule(self, advice_id: str) -> bool:
        return advice_id in self._compiled

    def missing(self, advice_id: str, text: str) -> list[str]:
        """Pattern sources NOT satisfied by `text` (empty list = safe)."""
        return [
            src
            for src, rx in zip(self._sources.get(advice_id, []), self._compiled.get(advice_id, []))
            if not rx.search(text)
        ]

    def hint(self, advice_id: str) -> str:
        return self._hints.get(advice_id, "")

    def with_prefix(self, advice_id: str, text: str) -> str | None:
        prefix = self._prefixes.get(advice_id)
        if not prefix or text.lower().startswith(prefix.strip().lower()):
            return None
        return prefix + lower_first(text)
