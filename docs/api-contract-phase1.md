# Phase 1 API 说明

这不是《Demo 接口契约 V0.1》。V0.1 不在仓库中。字段可以在契约补齐后替换。

前缀：`/api/v1`。

成功：

```json
{"code":"SUCCESS","message":"操作成功","details":null,"requestId":"请求追踪标识","data":{}}
```

失败不包含 `data`。校验失败的 `details` 是 `{loc,msg,type}` 列表，不回显被拒绝的原始输入。

| 状态 | code | 场景 |
| --- | --- | --- |
| 401 | UNAUTHORIZED | 未登录、会话过期、用户名或密码错误、账号停用 |
| 403 | FORBIDDEN | 已登录但不是管理员，访问 `/admin/status` |
| 404 | NOT_FOUND | 项目不存在，或项目属于其他用户 |
| 409 | CONFLICT | 同一账号下项目重名 |
| 422 | VALIDATION_ERROR | 参数结构或 Base URL 不合法 |
| 500 | INTERNAL_ERROR | 未处理异常，响应不包含内部信息 |
| 503 | DATABASE_UNAVAILABLE | 健康检查无法访问数据库 |

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| GET | `/health` | 否 | 数据库 `SELECT 1`，返回 phase1 |
| POST | `/auth/login` | 否 | 设置 Cookie `zhitest_session` |
| POST | `/auth/logout` | 是 | 撤销当前会话并清除 Cookie |
| GET | `/auth/me` | 是 | 当前用户，不含口令 |
| GET | `/auth/audit` | 是 | 当前用户最近 20 条审计，不返回 IP |
| POST | `/projects` | 是 | 创建项目，201 |
| GET | `/projects` | 是 | 只返回自己的项目，支持 `q`、`page`、`pageSize` |
| GET | `/projects/{id}` | 是 | 自己的项目详情 |
| GET | `/dashboard/summary` | 是 | 工作台。无执行数据时 `passRate` 为 null |
| GET | `/admin/status` | 管理员 | 用户数和项目数 |

登录失败对“用户不存在”和“密码错误”使用同一句“用户名或密码错误”。密码正确但账号停用时返回“账号已停用，请联系管理员”。
