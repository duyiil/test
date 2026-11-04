#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/zhitest/backend"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://zhitest:zhitest@127.0.0.1:5432/zhitest}"
export ZHITEST_ENV="${ZHITEST_ENV:-development}"
export ZHITEST_AUTO_BOOTSTRAP="${ZHITEST_AUTO_BOOTSTRAP:-true}"
export ZHITEST_ADMIN_USERNAME="${ZHITEST_ADMIN_USERNAME:-admin}"
export ZHITEST_ADMIN_PASSWORD="${ZHITEST_ADMIN_PASSWORD:-ChangeMe-Admin-2026}"
export ZHITEST_COOKIE_SECURE="${ZHITEST_COOKIE_SECURE:-false}"
export ZHITEST_LOG_LEVEL="${ZHITEST_LOG_LEVEL:-INFO}"
alembic upgrade head
exec uvicorn app.main:app --host 127.0.0.1 --port 8000
