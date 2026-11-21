
import os
import json
import re
import torch
from copy import deepcopy
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from lmformatenforcer import JsonSchemaParser, CharacterLevelParserConfig
from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn


class AdviceEngine:
    def __init__(self, base_dir=None):
        HERE = base_dir or os.path.dirname(os.path.abspath(__file__))

        with open(os.path.join(HERE, "advice_catalog.json"), "r", encoding="utf-8") as f:
            self.catalog = json.load(f)
        with open(os.path.join(HERE, "ecowatt_system_prompt.txt"), "r", encoding="utf-8") as f:
            self.system_prompt = f.read()
        with open(os.path.join(HERE, "ecowatt_safety_rules.json"), "r", encoding="utf-8") as f:
            self.safety_rules = json.load(f)
        with open(os.path.join(HERE, "ecowatt_required_prefixes.json"), "r", encoding="utf-8") as f:
            self.required_prefixes = json.load(f)

        self.min_advice = 3
        self.max_advice = 6
        self.model_id = "Qwen/Qwen3-4B-Instruct-2507"

        print("Loading Qwen3-4B-Instruct-2507...")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            quantization_config=bnb,
            device_map="auto",
            torch_dtype=torch.float16,
        )
        self.model.eval()
        print("Advice Engine loaded successfully.")

    def _parse_json(self, raw):
        if not raw or not raw.strip():
            return False, None, "Empty"
        def pairs(p):
            d = {}
            for k, v in p:
                if k in d:
                    raise ValueError(f"Duplicate key {k}")
                d[k] = v
            return d
        try:
            return True, json.loads(raw, object_pairs_hook=pairs), None
        except Exception as e:
            return False, None, str(e)

    def _safe(self, aid, text):
        rules = self.safety_rules.get(aid, [])
        return all(re.search(r, text.casefold()) for r in rules) if rules else True

    def _schema(self, allowed_ids=None, force_single=False):
        ids = [a["advice_id"] for a in self.catalog]
        if allowed_ids:
            ids = [i for i in ids if i in allowed_ids]
        return {
            "type": "object",
            "properties": {
                "advice": {
                    "type": "array",
                    "minItems": 1 if force_single else self.min_advice,
                    "maxItems": 1 if force_single else min(self.max_advice, len(ids)),
                    "items": {
                        "type": "object",
                        "properties": {
                            "advice_id": {"type": "string", "enum": ids},
                            "personalized_advice": {"type": "string", "minLength": 1},
                        },
                        "required": ["advice_id", "personalized_advice"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["advice"],
            "additionalProperties": False,
        }

    def _generate(self, context_payload, allowed_ids=None, force_single=False, feedback=None):
        sys_prompt = self.system_prompt
        if force_single:
            sys_prompt = (
                "You are repairing one EcoWatt advice item. "
                "Return exactly one JSON advice item using the supplied advice ID only. "
                'Format: {"advice":[{"advice_id":"<id>","personalized_advice":"<sentence>"}]}'
            )
        payload = deepcopy(context_payload)
        if feedback:
            payload["repair_errors"] = feedback

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        inputs = self.tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
            return_dict=True, return_tensors="pt",
        ).to(self.model.device)
        start = inputs["input_ids"].shape[-1]

        parser = JsonSchemaParser(
            self._schema(allowed_ids, force_single),
            config=CharacterLevelParserConfig(
                max_consecutive_whitespaces=1,
                force_json_field_order=True,
            ),
        )
        fn = build_transformers_prefix_allowed_tokens_fn(self.tokenizer, parser)

        with torch.inference_mode():
            out = self.model.generate(
                **inputs,
                max_new_tokens=220 if force_single else 640,
                do_sample=False, use_cache=True,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                prefix_allowed_tokens_fn=fn,
            )
        return self.tokenizer.decode(out[0, start:], skip_special_tokens=True).strip()

    def _enforce_safety(self, advice_list, context_payload):
        repaired = []
        for item in advice_list:
            aid = item["advice_id"]
            text = item["personalized_advice"]

            if self._safe(aid, text):
                repaired.append(item)
                continue

            missing = [p for p in self.safety_rules[aid] if not re.search(p, text.casefold())]
            single_ctx = deepcopy(context_payload)
            single_ctx["available_advice"] = [a for a in self.catalog if a["advice_id"] == aid]
            try:
                raw = self._generate(
                    single_ctx, allowed_ids=[aid], force_single=True,
                    feedback=["Your sentence MUST contain these EXACT phrases, verbatim: "
                              + " | ".join(missing)],
                )
                ok, parsed, _ = self._parse_json(raw)
                if (ok and parsed["advice"]
                    and parsed["advice"][0]["advice_id"] == aid
                    and self._safe(aid, parsed["advice"][0]["personalized_advice"])):
                    repaired.append(parsed["advice"][0])
                    continue
            except Exception:
                pass

            prefix = self.required_prefixes.get(aid, "")
            if prefix:
                base = text[5:] if text.lower().startswith("eco, ") else text
                if not base.lower().startswith(prefix.lower().strip()):
                    base = prefix + (base[0].lower() + base[1:] if base else "")
                repaired.append({"advice_id": aid, "personalized_advice": base})
            else:
                repaired.append(item)
        return repaired

    def generate_advice(self, user_profile, period, analysis):
        context_payload = {
            "household_profile": user_profile,
            "period": period,
            "analysis": analysis,
            "available_advice": self.catalog,
            "min_advice": self.min_advice,
            "max_advice": self.max_advice,
        }
        raw = self._generate(context_payload)
        ok, parsed, err = self._parse_json(raw)
        if not ok:
            raise ValueError(f"Model produced invalid JSON: {err}")

        safe = self._enforce_safety(parsed["advice"], context_payload)

        first_name = (user_profile.get("first_name") or "").strip()
        if safe and first_name and not safe[0]["personalized_advice"].lower().startswith(first_name.lower()):
            safe[0]["personalized_advice"] = f"{first_name}, {safe[0]['personalized_advice']}"
        return safe
