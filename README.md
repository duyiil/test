# 基于大语言模型智能体的软件自动化测试与质量保障平台
一次小实验

智测 ZhiTest。当前进度包含 Phase 1 基础工程，以及 Phase 2 主链路：Mock 生成、审核、本机 HTTP 执行、四种断言和数据报告。OpenAPI 导入、真实模型和源码执行还没有做。说明见 `docs/phase2.md`。演示服务是这次新写的，见 `demo/sut/README.md`。

## 资料缺口

仓库里没有《需求文档 V1.3》《架构设计 V0.1》《Demo 接口契约 V0.1》《团队开发规范 V1.0》、`智测原型.html` 和 `demo/sut/main.py`。Sprint 与测试用例以 `敏捷开发Sprint追踪表(2).xlsx`、`测试用例及跟踪(2).xlsx` 为准。冲突和默认值写在 `docs/phase0-audit.md`、`docs/assumptions.md`。

## 本地运行

```bash
cd zhitest/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
./../../scripts/dev-api.sh
```

另一个终端：

```bash
cd zhitest/frontend
npm install
npm run dev
```

打开 http://127.0.0.1:5173 。默认开发账号来自环境变量，示例是 `admin` / `ChangeMe-Admin-2026`（见 `.env.example`）。这不是生产口令。首版不能注册。

验证：

```bash
./scripts/verify.sh
```

## 一键部署

前提：已安装 Docker Engine 或 Docker Desktop（Compose v2），当前用户能运行 `docker`。Linux、macOS、Windows 都用官方多架构镜像（`postgres:16`、`python:3.12-slim`、`node:22-alpine`、`nginx:1.27-alpine`），不绑定某一种 CPU。Windows 请在 Git Bash 或 WSL 里执行下面的脚本。

```bash
./scripts/install.sh --demo
```

不需要演示被测服务时，去掉 `--demo`。脚本会在没有 `.env` 时从 `.env.example` 生成一份，写入随机的数据库口令、`ZHITEST_SECRET_KEY` 和管理员密码，并只在终端打印一次管理员密码。`.env` 已在 `.gitignore` 里，不要提交。DeepSeek 密钥留在 `ZHITEST_LLM_API_KEY`，空着就继续用 Mock。

打开 http://127.0.0.1:8080 。用户名是 `admin`。密码是刚才打印的那一行；错过了就看 `.env` 里的 `ZHITEST_ADMIN_PASSWORD`。带 `--demo` 时，项目的 Base URL 填 `http://sut:9000`（这是容器网络里的演示服务，不是执行器自己的 127.0.0.1）。

常用操作：

```bash
docker compose ps
docker compose stop
docker compose up -d
docker compose pull
docker compose up -d --build
docker compose down
docker compose down -v
```

`down -v` 会删掉数据库卷，等于清空后重来。升级是重新执行 `./scripts/install.sh`（已有 `.env` 时不会重写密码）；API 启动时会执行一次 `alembic upgrade head`，Worker 等 API 健康后再启动，不会再跑迁移。

如果 API 一直起不来，先看 `docker compose logs api`。容器之间连不上 Postgres、而宿主机连已发布端口却正常时，常见原因是宿主机同时留着 iptables-nft 和 iptables-legacy，且 legacy 的 `FORWARD` 策略是 `DROP`。这是机器上的防火墙残留，不是 Compose 里的服务名写错。处理后再启动：

```bash
sudo iptables-legacy -P FORWARD ACCEPT
```

不要在脚本里改宿主机防火墙。Docker Desktop 的新机器通常没有这套残留规则。

## 目录

- `zhitest/backend`：FastAPI、迁移、pytest
- `zhitest/frontend`：React + TypeScript + Vite
- `compose.yaml`：一键部署。`deploy/docker-compose.yml` 只是指向它
- `docs`：审计、接口、数据库、运行、追踪
- `scripts`：本地启动和验证

Phase 1 接口见 `docs/api-contract-phase1.md`。不要把它当成缺失的契约 V0.1。
