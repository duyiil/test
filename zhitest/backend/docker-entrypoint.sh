#!/bin/sh
# 先等数据库端口，再由 API 进程执行一次迁移。Worker 只等待，不重复迁移。
set -eu

python - << 'PY'
import os
import socket
import sys
import time
from urllib.parse import urlparse

raw = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://", 1)
parsed = urlparse(raw)
host = parsed.hostname or "postgres"
port = parsed.port or 5432
last = "未连接"
for attempt in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            break
    except OSError as exc:
        last = str(exc)
        print(f"等待数据库 {host}:{port} ({attempt + 1}/60)", flush=True)
        time.sleep(1)
else:
    print(f"数据库不可达 {host}:{port}: {last}", file=sys.stderr)
    sys.exit(1)
PY

if [ "${1:-}" = "worker" ]; then
  exec python -m app.worker
fi

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
