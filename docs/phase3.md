# 本轮增量

团队原文仍然缺失，见 `docs/missing-originals.md`。没有把它们写出来。

已实现并有自动化测试的部分：

- OpenAPI 3.x JSON/YAML 预览后确认导入，再交给生成器。
- 用例集、依赖排序、`{{var}}` 提取。依赖链示例会创建“创建后查询”。
- Idempotency-Key：相同参数返回原任务，不同参数 409。
- Worker 租约过期后恢复，已完成步骤不重放；进行中的写请求标为 unknown，不自动重放。
- SSRF：解析 DNS，拒绝私网、回环、链路本地和元数据地址。`127.0.0.1` 只因为允许名单而放行。重定向目标会再检查一次。
- 未登录时畸形 JSON 返回 401。登录接口本身仍返回 422。
- 两小时会话用可替换时钟验证，不是墙钟等待。
- 模型调用是 OpenAI 兼容格式，默认 `https://api.deepseek.com` 和 `deepseek-chat`。没有 `ZHITEST_LLM_API_KEY` 时生成仍用 Mock，研判状态保持 unavailable。密钥不入库、不写日志。
- 生成请求使用 JSON mode，并给出 method、relativePath、statusCode、jsonType、equals、range 的示例。模型若仍返回 `request.method/path` 或 `status`、`bodyPath`，会先归一化再校验；单条不合法会写明用例名，合法条目仍保存。生成任务记录实际 provider 和 model。研判会带上失败用例的期望、实际和截断脱敏后的响应片段；研判异常会记脱敏日志，并把 `aiStatus=failed` 和原因写入报告。研判正文上限是 12000 字，并限制 `max_tokens`；仍然超长时停在句号或换行，末尾写「（已截断）」。`jsonType` 期望 `number` 时接受整数。
- OpenAPI 路径参数没有 example 时按类型给默认值（integer/number 为 1，string 为 example），并在预览的 warnings 里标明。不再一律写成 `sample`。

部分实现、不能当成完成：

- 多环境、归档、删除、成员、批量审核、HTML/JSON 报告导出、站内通知、候选缺陷、cron 记录。页面没有把这些全部做成完整管理界面。
- 调度函数只处理已经到期的记录，没有验证操作系统级 cron 一直在跑。
- PDF 导出没有做。

Docker Compose 的实际运行结果写在阶段报告里，以命令输出为准。
