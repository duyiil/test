#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/zhitest/backend/.venv/bin/python" ]]; then
  exec "$ROOT/zhitest/backend/.venv/bin/python" demo/sut/main.py
fi
exec python3 demo/sut/main.py
