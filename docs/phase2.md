# Phase 2 说明

本阶段补的是主链路：Mock 生成、审核、独立 Worker 执行、四种断言、数据报告，以及一个作者自建的演示服务。

没有使用真实模型，也不需要模型密钥。`MockGenerationProvider` 只读项目里保存的契约。演示服务在 `demo/sut/`，缺陷说明写在该目录的 README，是这次新写的，不是仓库里原本缺失的团队 Demo。

执行器只允许访问 `127.0.0.1`、`localhost`、`::1`。没有做 OpenAPI 导入、变量依赖链、幂等键、租约 fencing、真实 LLM 研判，也没有执行用户源码。

数据报告和 AI 分析分开。AI 状态固定为 `unavailable`，因为没有配置真实研判模型。Mock 生成不会被写成 AI 分析结论。

Worker 是 `python -m app.worker`，轮询 PostgreSQL。没有引入 Celery / Redis：任务状态已经在数据库里，Phase 1 也没有 Redis。

本地需要三个进程：API、Worker、演示服务，再加上前端。

```bash
./scripts/dev-api.sh
./scripts/dev-worker.sh
./scripts/dev-sut.sh
cd zhitest/frontend && npm run dev
```

项目 Base URL 使用 `http://127.0.0.1:8001`。页面上先「载入演示契约」，再「生成测试草稿」。草稿提交审核并通过后，在执行页确认写操作并入队。Worker 跑完后可以打开数据报告。
