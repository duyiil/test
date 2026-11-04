# Phase 0 审计（2026-11-04）

审计对象是仓库当前 `main` 工作区，外加 git 历史里已被删除的表格。没有把缺失文档补写成“原件”。

## 1. 已找到的文件和代码

| 路径 | 说明 |
| --- | --- |
| `README.md` | 两行：项目标题“基于大语言模型智能体的软件自动化测试与质量保障平台”，以及“一次小实验”。 |
| `111` | 一行 `#China pepole can fly`。与智测功能无关，本次未改。 |
| `敏捷开发Sprint追踪表(2).xlsx` | 8 个工作表：需求列表、用户故事、Sprint1～Sprint5 迭代计划、迭代回顾。 |
| `测试用例及跟踪(2).xlsx` | 10 个工作表。用例编号 TC-PROJECT-001～TC-CONFIG-014，共 126 条。测试结果列为空。 |

仓库里没有前端、后端、Demo SUT、数据库迁移或测试代码。

Git 历史（提交 `d42ca74`，后于 `1a21baa` / `763b8a9` 删除）里还有更早的两份表格：

- `敏捷开发Sprint追踪表.xlsx`：学生/用户注册模板。Sprint1 日期写成 `2016/03/24~2026/04/7`。其中“用户注册开发 / 张三”被标成 Done。这不是智测功能。
- `测试用例及跟踪.xlsx`：学生管理模板，两条用例结果为 pass。

这两份已删除文件不作为智测需求基线，也不恢复进工作区。

## 2. 现有项目技术栈

没有可运行工程，因此没有既有技术栈。`README.md` 只有标题。Phase 1 采用任务说明里的默认可替换选型：React、TypeScript、Vite、Ant Design、React Router、Axios、TanStack Query、Zustand、ECharts；FastAPI、Pydantic、SQLAlchemy、Alembic、PostgreSQL、HTTPX、pytest。运行环境是 Python 3.12.3，不是 3.11。本环境没有 Docker。

## 3. 当前可运行的功能

审计开始时没有任何可运行功能。没有启动脚本，没有接口，没有数据库。

## 4. 已存在但尚未完成的功能

代码层面没有任何已开始的功能。表格里的用户故事 US-001～US-027 状态全部是 TODO。126 条测试用例都没有填写测试结果。

## 5. 与 Sprint 表不一致的地方

任务说明里的 Sprint 划分和仓库中的 `敏捷开发Sprint追踪表(2).xlsx` 不是同一份计划。指定文件名《敏捷开发Sprint追踪表_第三组_V3.xlsx》不存在，现有表格也没有“第三组”或“V3”字样。下面按现有表格原文对照任务说明，不改表格中的需求。

| 主题 | 任务说明 | 仓库中的 Sprint 表 |
| --- | --- | --- |
| Sprint1（2026/10/13～2026/10/26） | 需求、原型、架构、契约、规范、用例表 | US-001～US-005：项目、OpenAPI 导入、手工录入、LLM 生成。全部 TODO。 |
| Sprint2（2026/10/27～2026/11/09） | 登录、项目、Mock Provider、用例审核、Worker、四种断言、报告、Demo SUT | US-006～US-012：审核、执行、研判、报告、通知、模型配置。全部 TODO。项目 CRUD 在表里属于 Sprint1。 |
| Sprint3 | OpenAPI、变量、幂等、任务恢复、真实 LLM | US-013～US-016：定时、回归集、缺陷、指派。 |
| Sprint4 | Python 源码测试闭环 | US-017～US-022：批量审核、报告导出、变量、预算、角色、用例库。表中没有 Python 源码测试。 |
| Sprint5 | 通知、管理员配置、部署验收 | US-023～US-027：Web、小程序、Jira/禅道、质量看板、多轮对话。通知和模型配置在表里属于 Sprint2。 |
| 验收编号 | US-01～US-10、AC-01～AC-26 | 只有 US-001～US-027 和 TC-*。没有 AC-01～AC-26。AC 全部标为待核对。 |
| 进度 | 不要把标成 Done 的功能当成已实现 | 智测表格没有任何 Done。历史模板里的 Done 不属于智测。 |

今天是 2026-11-04，日历落在两份计划共同的 Sprint2 日期里。表格中的 Sprint1 任务仍是 TODO，代码也未开始，所以不能把 Sprint2 主链路当成已有基础。

## 6. 可以直接复用的组件

没有可复用的页面、接口或迁移。可直接引用的只有：

- 现有 Sprint 表里的 US / TC 编号和日期。
- 126 条测试用例的步骤与预期，用作后续追踪，不表示已经通过。
- README 的项目标题。

## 7. 必须补充的文件或依赖

任务说明点名、但仓库中不存在的资料：

- 《需求文档 V1.3》
- 《架构设计 V0.1》
- 《Demo 接口契约 V0.1》（因此也不存在其中所说的 6 张基础表）
- 《团队开发规范 V1.0》
- `智测原型.html`
- `demo/sut/main.py`
- 数据库迁移与既有测试代码

Phase 1 需要新补的工程依赖：Python 包（FastAPI、SQLAlchemy、Alembic、psycopg、bcrypt、pytest）、Node 包（React、Ant Design、Vite 等）、PostgreSQL。Docker Compose 文件会写入仓库；当前机器没有 Docker，不能把它算作已验证。

## 8. 当前阶段任务清单

Phase 1 基础工程，对应任务说明第十四部分，不把 Sprint2 主链路标成完成：

1. React + TypeScript + Vite 前端。
2. Ant Design 后台布局。
3. FastAPI 入口。
4. PostgreSQL 连接。
5. SQLAlchemy + Alembic。
6. 环境变量配置。
7. 统一异常。
8. requestId。
9. 登录、退出、当前用户。
10. 管理员安全初始化。
11. 服务端项目归属检查。
12. 项目创建、列表、详情。
13. 工作台真实计数接口。
14. 结构化日志与操作审计。
15. 健康检查。
16. Docker Compose，以及在没有 Docker 时可用的本地运行脚本。
17. README 与自动化测试。

明确不做：Mock 生成、用例审核、执行 Worker、四种断言、报告、OpenAPI 导入、真实 LLM、源码执行、通知、Demo SUT。
