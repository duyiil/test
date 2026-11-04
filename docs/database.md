# Phase 1 数据库

迁移：`zhitest/backend/alembic/versions/0001_phase1_foundation.py`，修订号 `0001_phase1`。

时间字段都是 `timestamptz`。主键是 UUID。没有保存明文口令或会话原文，会话表只存 SHA-256。

| 表 | 作用 | 约束 |
| --- | --- | --- |
| `users` | 账号 | `username` 唯一；`role` 只能是 `admin` 或 `member` |
| `user_sessions` | 登录会话 | `token_hash` 唯一；过期时间、撤销时间 |
| `projects` | 项目 | `(owner_id, name)` 唯一；`owner_id` 外键 |
| `audit_logs` | 操作审计 | 记录动作、资源、请求号、IP；登录失败也会单独提交 |

Phase 1 没有用例、执行、报告、模型密钥表。因此也不存在“修改历史版本”或“报告被当前用例改写”的数据路径。这些约束留到对应表出现时再加。

删除用户不是本阶段功能。项目所有者外键是 `RESTRICT`，会话是 `CASCADE`，审计操作者是 `SET NULL`。
