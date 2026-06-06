#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="${PWD}/vendor:${PYTHONPATH:-}"
exec python3 -m uvicorn app:app --host 0.0.0.0 --port 8765 --reload "$@"
