# 基于大语言模型智能体的软件自动化测试与质量保障平台
一次小实验

智测 ZhiTest。当前仓库进度是 **Phase 1 基础工程**：可以登录、按所有者隔离项目、查看真实工作台数据。用例生成、审核、执行、报告、OpenAPI 导入和源码测试都还没有做。

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

Docker 编排在 `deploy/docker-compose.yml`。编写时的环境没有 Docker，Compose 没有被执行过。步骤见 `docs/runbook.md`。

## 目录

- `zhitest/backend`：FastAPI、迁移、pytest
- `zhitest/frontend`：React + TypeScript + Vite
- `deploy`：Compose
- `docs`：审计、接口、数据库、运行、追踪
- `scripts`：本地启动和验证

Phase 1 接口见 `docs/api-contract-phase1.md`。不要把它当成缺失的契约 V0.1。
