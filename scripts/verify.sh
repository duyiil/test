#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/zhitest/backend"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif [[ -f .venv/Scripts/activate ]]; then
  # shellcheck disable=SC1091
  # Windows venv 布局：activate 在 Scripts/ 下
  source .venv/Scripts/activate
fi
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://zhitest:zhitest@127.0.0.1:5432/zhitest_test}"
export ZHITEST_ENV=test
export ZHITEST_AUTO_BOOTSTRAP=false
export ZHITEST_ADMIN_USERNAME=admin
export ZHITEST_ADMIN_PASSWORD=Admin_Pass_123
export ZHITEST_LOG_LEVEL=WARNING
alembic upgrade head
pytest -q
cd "$ROOT/zhitest/frontend"
npm run build
