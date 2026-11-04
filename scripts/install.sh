#!/bin/sh
# 生成 .env（若缺失）并启动智测。可选：./scripts/install.sh --demo
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$ROOT"

PROFILE=""
if [ "${1:-}" = "--demo" ]; then
  PROFILE="--profile demo"
fi

rand() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_urlsafe(18))'
  elif command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | cut -c1-24
  else
    echo "需要 python3 或 openssl 来生成密码" >&2
    exit 1
  fi
}

if [ ! -f .env ]; then
  admin_password=$(rand)
  secret_key=$(rand)$(rand)
  pg_password=$(rand)
  awk -v pass="$admin_password" -v secret="$secret_key" -v pg="$pg_password" '
    BEGIN {
      keys["ZHITEST_ADMIN_PASSWORD"] = pass
      keys["ZHITEST_SECRET_KEY"] = secret
      keys["POSTGRES_PASSWORD"] = pg
    }
    {
      split($0, parts, "=")
      key = parts[1]
      if (key in keys) {
        print key "=" keys[key]
        seen[key] = 1
      } else {
        print
      }
    }
    END {
      if (!("ZHITEST_SECRET_KEY" in seen)) print "ZHITEST_SECRET_KEY=" secret
      if (!("POSTGRES_PASSWORD" in seen)) print "POSTGRES_PASSWORD=" pg
      if (!("POSTGRES_USER" in seen)) print "POSTGRES_USER=zhitest"
      if (!("POSTGRES_DB" in seen)) print "POSTGRES_DB=zhitest"
    }
  ' .env.example > .env
  chmod 600 .env
  echo "已生成 .env。管理员密码只在这次打印，同时写在 .env 里，不会提交到仓库。"
  echo "管理员用户名: admin"
  echo "管理员密码: ${admin_password}"
else
  echo ".env 已存在，继续使用其中的管理员密码。忘记时请查看 .env 的 ZHITEST_ADMIN_PASSWORD。"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "未找到 docker。请先安装 Docker Engine 或 Docker Desktop。" >&2
  exit 1
fi

# shellcheck disable=SC2086
exec docker compose --env-file .env -f compose.yaml $PROFILE up -d --build
