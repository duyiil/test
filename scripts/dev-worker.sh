#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/zhitest/backend"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://zhitest:zhitest@127.0.0.1:5432/zhitest}"
export ZHITEST_LOG_LEVEL="${ZHITEST_LOG_LEVEL:-INFO}"
exec python -m app.worker
