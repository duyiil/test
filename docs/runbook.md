# 运行手册

## 本地（本次实际使用的方式）

需要 PostgreSQL 16，以及 Python 3.11+ 和 Node.js 22。

```bash
sudo -u postgres psql -c "CREATE USER zhitest WITH PASSWORD 'zhitest';"
sudo -u postgres psql -c "CREATE DATABASE zhitest OWNER zhitest;"
sudo -u postgres psql -c "CREATE DATABASE zhitest_test OWNER zhitest;"
cd zhitest/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd ../frontend
npm install
```

启动 API（会先迁移开发库 `zhitest`）：

```bash
./scripts/dev-api.sh
```

另开一个终端启动前端：

```bash
cd zhitest/frontend
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。开发占位账号是 `admin` / `ChangeMe-Admin-2026`，只在环境变量没有改过时成立。不要把这个口令用于公网。

验证：

```bash
./scripts/verify.sh
```

脚本会迁移测试库、运行 pytest，并构建前端。

## Docker Compose

编排文件：`deploy/docker-compose.yml`。设计上一条命令是：

```bash
docker compose -f deploy/docker-compose.yml up --build
```

Web 为 `http://localhost:8080`，API 为 `http://localhost:8000`。2026-11-04 的执行环境没有 Docker，这一条没有实际跑过，不能算通过。

## 会话

Cookie 名 `zhitest_session`，HttpOnly、SameSite=Lax。本地 HTTP 不设置 Secure。空闲滑动超时默认 7200 秒。前端主题和当前项目选择放在 localStorage，项目草稿放在 sessionStorage。密码和令牌不写入这些存储。
