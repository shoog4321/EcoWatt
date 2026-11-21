# EcoWatt backend

```
Flutter ──Supabase session──> FastAPI (app/) ──REST──> Supabase (Postgres/Auth)
   │                               │
   └── reads Advice/advice_jobs    └── HTTPS (ngrok) ──> GPU service (gpu_service/) on Kaggle
       straight from Supabase           Qwen3-4B-Instruct-2507, 4-bit NF4, LM Format Enforcer, greedy decoding
```

## Folder layout
| Path | Contents |
|---|---|
| `app/` | FastAPI backend: bill validation, rule engine (Component A), advice jobs, OCR route (`/analyze-bill`) |
| `app/label_ocr.py`, `app/label_routes.py` | AC energy-label scanner (`POST /analyze-ac-label`) from the appliance-label OCR notebook: grade, capacity, efficiency, yearly kWh. Results only, nothing stored |
| `app/rule_engine.py` | `SaudiElectricityAnalyzer` ported to stdlib Python; identical results to the notebook (42 sample bills + 600 random households) |
| `gpu_service/` | The evaluated `advice_engine.py` (byte-identical) and the bill OCR (`invoice_ocr.py`, copy of `app/`) behind HTTP, plus `kaggle_launch.ipynb` |
| `handoff/` | The 4 model hand-off files the GPU service loads (catalog, system prompt, safety rules, required prefixes) |
| `data/` | Backend copy of `advice_catalog.json` (must equal `handoff/`), the original evaluated catalog, and files for `ENGINE_MODE=openai` |
| `sql/` | `001` advice_jobs table + `Advice.catalog_advice_id`; `002` the 130 consumption baselines |
| `scripts/build_kaggle_zip.sh` | Builds `dist/ecowatt-gpu.zip` (gpu_service + handoff) for the Kaggle Dataset |
| `scripts/analyze_existing_bills.py` | Analyses bills saved before the backend existed and queues advice for each home's newest bill (`--dry-run` to preview) |
| `tests/` | Unit tests, stdlib only (no GPU, no network); `test_api` needs the venv |

Flow: user confirms a bill → app saves it → `POST /bills/{id}/analyze` → backend validates it (tariff check), runs the
rule engine, stores the headline numbers on the `Bill` row and queues advice → the advice screen shows "Preparing..."
until `advice_jobs.status = done`, then reads the `Advice` rows.

## Setup
1. **Supabase** (SQL editor): run `sql/001_advice_jobs.sql`, then `sql/002_consumption_baselines_seed.sql`.
2. **Backend**
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   cp .env.example .env      # fill in SUPABASE_URL, SUPABASE_ANON_KEY (publishable), SUPABASE_SERVICE_KEY (secret),
                             # a random ADMIN_TOKEN and LLM_API_KEY
   .venv/bin/uvicorn app.main:app --env-file .env --port 8080
   ```
3. **GPU (Kaggle)**
   - `./scripts/build_kaggle_zip.sh`, then upload `dist/ecowatt-gpu.zip` as a private Kaggle Dataset.
   - Import `gpu_service/kaggle_launch.ipynb`, set GPU T4 + Internet on, add the dataset as input, and add the secrets
     `GPU_API_KEY` (= `LLM_API_KEY` in `.env`) and `NGROK_AUTH_TOKEN`.
   - Run all cells in order in every new session (installs included; no restart needed). Model download + load takes 5-10 minutes.
4. **Connect** the backend to the URL the notebook prints: set `LLM_BASE_URL` in `.env`, or
   `PUT /admin/llm-endpoint` with header `X-Admin-Token`. `GET /health/llm` must show `llm_reachable: true` and
   `catalog_matches_backend: true`.
5. **Flutter app** (the app project already contains all backend integration changes):
   ```bash
   flutter run -d chrome --web-port 5050 --dart-define=API_BASE_URL=http://127.0.0.1:8080
   ```
   (iOS Simulator: same command with `-d <simulator>`; on a physical phone use the Mac's LAN IP or a deployed URL.)

Tests (no GPU, no network): `.venv/bin/python -m tests.test_api` (HTTP endpoints) and `for t in test_invoice_ocr test_rule_engine test_engine test_bills test_profiles test_jobs test_gpu_service test_gpu_client test_remote_engine; do python3 -m tests.$t; done`

## Advice catalog
`data/advice_catalog.json` and `handoff/advice_catalog.json` are the live catalog (55 items). The catalog used in the
model evaluation is kept unchanged as `data/advice_catalog.evaluated.json`. The live version corrects:
- ADV_001, 002, 003, 006, 031, 032, 033, 057: heating / heat-retention tips that were typed `cooling` or applied all year.
  They now say "In winter, ..." and have `applicability: "winter"`. In testing, a July bill produced "Lower your thermostat
  by 1°C to reduce cooling costs". The backend now also drops any winter-only item on a non-winter bill.
- ADV_059: said a console in sleep mode uses less power than one switched off. That is reversed now.

Catalog types that are not `advice_category_enum` values are mapped when the advice is saved: `heating` → `behavior`
and `appliances` → `laundry` (`app/jobs.py`).

The model is shown exactly the analysis fields it was evaluated on. `saving_kwh` is stored on the `Bill` but not sent to the model.

## Which tips the model may pick
For every bill the backend sends the GPU service a list of excluded catalog ids, which are hidden from the model for
that request (`excluded_ids` in `app/advice_engine.py`):
- winter-only tips (`applicability: "winter"`) outside December–February
- tips marked `requires_purchase` (14 items: LED bulbs, smart thermostat, power strips, ...) when the household answered
  No to "willing to upgrade appliances"
- tips the household already marked as applied, **if the new bill's consumption dropped** compared with its previous
  bill (the tips seem to have worked, so new ones follow). If consumption stayed the same or went up, applied tips may
  be suggested again rather than falling back to unrelated advice. If too few tips remain, applied ones are allowed
  again. The job's `audit` records which case applied (`applied_tips`).

The backend also drops any excluded id that still comes back, before saving.

## AC energy-label scanning
The Home screen's "Check your AC's energy label" card opens a bottom sheet: the user takes or chooses a photo of the
SASO label and sees the grade (A–G with a plain-language meaning), cooling capacity (BTU/h, kW and tons), efficiency
value and the label's yearly kWh. Nothing is saved. The scanner runs on the backend CPU with PaddleOCR's mobile
models (~10–15 s per photo): `.venv/bin/pip install -r requirements-label.txt`. Without it the endpoint answers 503
with a readable message. Notebook evaluation on 10 labels: grade 100%, kW / BTU / efficiency 80%, yearly kWh 70%,
so the sheet asks users to compare the values with their label.

## Known limitations
- The Kaggle session stops after ~30 min idle / 12 h. Advice jobs stay `pending` and are retried every 60 s once the GPU is back.
- Bill scanning (`/analyze-bill`) runs on the Kaggle GPU (a few seconds). If the GPU is unreachable it falls back to the
  backend's CPU, which needs `pip install -r requirements-ocr.txt` and takes minutes per image on a laptop.
- Scanning was checked on two real SEC bills: a full-size one reads month, amount and kWh correctly (tariff-verified);
  a 580 px screenshot does not. Scanning accuracy depends on image resolution: low-resolution screenshots (e.g. 600 px wide) are often misread;
  users should check the filled-in values, which the form already asks them to do.
- The app analyzes newly added bills only. Bills saved some other way need `scripts/analyze_existing_bills.py`.
- New advice appears when the next bill is added; applying all tips does not trigger a new set by itself.
- Editing a bill re-runs the analysis. Its advice is regenerated unless the user already applied some of it; then the
  advice (and that progress) is kept and only the numbers are updated.

## When the GPU is off
Generation is asynchronous. If the GPU host is unreachable, the job stays `pending` and a sweeper retries every 60 s.
Deterministic failures (the model returns unusable output) become `failed`. The app then shows a Retry button
(`POST /bills/{id}/advice/regenerate`). Advice is stored in Supabase, so a demo works with the GPU off if the advice
was generated beforehand.

## Engine modes
`ENGINE_MODE=gpu_service` (default): the evaluated engine. `ENGINE_MODE=openai`: a vLLM fallback with the prompt and
safety layer re-implemented in `app/advice_engine.py`. It is NOT the evaluated configuration (FP16 vLLM instead of
4-bit NF4 + LM Format Enforcer).
