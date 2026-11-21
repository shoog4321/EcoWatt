Files the backend reads from this folder:

  advice_catalog.json            REQUIRED. Live catalog (55 items). Must be byte-identical to handoff/advice_catalog.json
                                 on the GPU host; the backend compares SHA-256 hashes and refuses advice otherwise.
  advice_catalog.evaluated.json  The original catalog used in the model evaluation (kept for reference; not loaded).
                                 See "Advice catalog" in the main README for what changed and why.

Only for ENGINE_MODE=openai (the default gpu_service mode loads these on the GPU host from handoff/):
  system_prompt.txt              <- copy of handoff/ecowatt_system_prompt.txt (not included)
  safety_rules.json, required_prefixes.json   (layout {advice_id: {"patterns": [...], "hint": "..."}})

Catalog fields added for the live version: `applicability` ("all" | "winter") and `requires_purchase` (bool);
see "Which tips the model may pick" in the main README.

Catalog `approved_type` values that are not advice_category_enum values are mapped by app/jobs.py
(CATEGORY_ALIASES): heating -> behavior, appliances -> laundry.

NOTE: the "EcowattTips" table in Supabase is not used by the backend; the catalog file is the source of truth.
