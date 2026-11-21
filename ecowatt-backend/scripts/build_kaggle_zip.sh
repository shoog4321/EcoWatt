#!/bin/sh
# Builds dist/ecowatt-gpu.zip for the Kaggle Dataset: gpu_service/ (advice engine + bill OCR) + handoff/ (the 4 model files).
# Upload it as a new dataset version whenever gpu_service/ or handoff/ changes; the backend refuses to generate
# advice if the GPU host's advice_catalog.json differs from data/advice_catalog.json.
set -e
cd "$(dirname "$0")/.."
cmp -s handoff/advice_catalog.json data/advice_catalog.json || { echo "handoff/ and data/ catalogs differ" >&2; exit 1; }
cmp -s gpu_service/invoice_ocr.py app/invoice_ocr.py || { echo "gpu_service/invoice_ocr.py differs from app/invoice_ocr.py" >&2; exit 1; }
mkdir -p dist && rm -f dist/ecowatt-gpu.zip
zip -qr dist/ecowatt-gpu.zip gpu_service/__init__.py gpu_service/server.py gpu_service/service.py \
    gpu_service/advice_engine.py gpu_service/invoice_ocr.py handoff -x '*.DS_Store' '*__pycache__*'
echo "built dist/ecowatt-gpu.zip"
