# EcoWatt

**Intelligent Assistance for Sustainable Household Electricity Consumption**

EcoWatt helps households in Saudi Arabia understand and reduce their electricity use. Users enter or scan their
monthly SEC bill; the system compares it with regional baselines for similar homes, explains what drives the
consumption and generates personalised, safety-checked saving advice with a language model (Qwen3-4B-Instruct). The app can
also read an air conditioner's SASO energy-efficiency label and explain it.

## Contents

| Folder | Description |
|---|---|
| `ecowatt-app/` | Flutter mobile application (iOS, Android, web) |
| `ecowatt-backend/` | FastAPI backend: bill validation, rule engine, advice jobs, bill and AC-label scanning, GPU service, database scripts and tests |

## System architecture

```
Flutter app ──Supabase session──> FastAPI backend ──REST──> Supabase (Postgres + Auth)
     │                                  │
     └─ reads advice from Supabase      └─ HTTPS ──> GPU service (Kaggle T4)
                                                      Qwen3-4B-Instruct-2507, 4-bit NF4, LM Format Enforcer
                                                      EasyOCR for bill scanning
```

| Component | Role |
|---|---|
| Rule engine | Classifies consumption (Low / Average / Moderate / High) against 130 regional baselines (region × season × housing type) and identifies the main drivers |
| Advice engine | Selects and writes 3–6 tips from a 55-item catalog, with a safety layer and per-household exclusions (season, purchases, applied tips) |
| Bill scanning | Reads month, amount and kWh from a photo of an SEC bill and checks them against the SEC tariff |
| AC label scanning | Reads grade, cooling capacity, efficiency and yearly kWh from a SASO energy label (PaddleOCR) and explains each value |

## Requirements

- Python 3.10 or newer
- Flutter 3.41 or newer
- A Supabase project, and a Kaggle account with GPU access for the advice model

## Setup

### 1. Database (Supabase SQL editor)
Run `ecowatt-backend/sql/001_advice_jobs.sql`, then `ecowatt-backend/sql/002_consumption_baselines_seed.sql`.

### 2. Backend
```bash
cd ecowatt-backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-label.txt     # AC energy-label scanner
cp .env.example .env                               # then fill in the Supabase keys and tokens
.venv/bin/uvicorn app.main:app --env-file .env --port 8080
```
`.env` holds the project's secret keys and is not included in this package. On Windows use `.venv\Scripts\` instead
of `.venv/bin/`.

### 3. GPU service (Kaggle)
Build the dataset with `./scripts/build_kaggle_zip.sh`, upload it as a private Kaggle Dataset, and run
`gpu_service/kaggle_launch.ipynb` on a T4 GPU. Connect the backend to the URL the notebook prints (`LLM_BASE_URL` in
`.env`). `http://localhost:8080/health/llm` then reports `"llm_reachable": true`. Full steps are in
`ecowatt-backend/README.md`.

### 4. App
```bash
cd ecowatt-app
flutter pub get
flutter run -d chrome --web-port 5050 --dart-define=API_BASE_URL=http://127.0.0.1:8080
```
For the iOS Simulator, run `open -a Simulator` and use `-d iPhone`. For the Android emulator use
`--dart-define=API_BASE_URL=http://10.0.2.2:8080`.

## Using the app

1. **Sign up** with name, email, phone (`05XXXXXXXX`) and password, then enter home details and answer the questionnaire.
2. **Bills**: add a bill by hand or scan a photo of it. Values that do not match the SEC tariff are rejected with an
   explanation. Bills can be edited.
3. **Advice**: 3–6 personalised tips appear about a minute after a bill is added. Tips can be marked as applied.
4. **Home**: latest bill, consumption trend, comparison with similar homes and estimated savings.
5. **Check your AC's energy label** (on Home): scan a SASO label to see its grade, what it means, cooling capacity,
   yearly consumption and a tip.

## Tests

```bash
cd ecowatt-backend
.venv/bin/python -m tests.test_api
for t in test_invoice_ocr test_rule_engine test_engine test_bills test_profiles test_jobs test_gpu_service test_gpu_client test_remote_engine; do python3 -m tests.$t; done

cd ../ecowatt-app
flutter test
flutter analyze
```
74 backend tests and 13 app tests pass; static analysis reports no issues.

## Limitations

- The GPU runs in Kaggle sessions (up to 12 hours, stopping when idle). While it is off, advice requests wait and are
  retried automatically every 60 seconds, and bill scanning falls back to the backend CPU (slower).
- Scanning accuracy depends on image quality; low-resolution images may be misread, so users review the values before
  saving.
- New advice is generated when a new bill is added.
