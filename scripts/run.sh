#!/usr/bin/env bash
# Arranca la app en http://127.0.0.1:8000 (crea y siembra la BD ficticia la primera vez)
set -e
cd "$(dirname "$0")/.."
python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
