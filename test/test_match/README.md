# test_match — 柴诗雨开发环节的测试用例

本目录存放柴诗雨三个开发环节的测试用例（pytest），覆盖：

1. **TriageProvider mock 研判**：无真实模型密钥时，按 7 类内置 bug 规则对断言失败输出归因（`backend/app/modules/ai/mock_triage.py`）
2. **数据访问层与默认项目种子数据**：bootstrap 阶段为管理员创建默认演示项目并载入演示契约（`backend/app/modules/seed.py`）
3. **demo/sut 被测服务联调**：端口 8001，7 个预埋 bug 可复现（`demo/sut/main.py`）

## 运行

```bash
# 用后端 venv 运行（复用已装依赖），测试库为 zhitest_test
E:/duyiil-test/zhitest/backend/.venv/Scripts/python.exe -m pytest E:/duyiil-test/test/test_match -v
```

## 用例清单

### 一、Mock 研判（TCM-TRIAGE）

| 编号 | 用例 | 预期 |
| --- | --- | --- |
| TCM-TRIAGE-001 | 规则表恰好覆盖 7 类内置 bug | 7 条规则，key 与 7 个缺陷一一对应 |
| TCM-TRIAGE-002 | 未知商品返回 200（契约 404）命中「未返回 404」规则 | 输出含标题与建议 |
| TCM-TRIAGE-003 | 缺少必填 name 仍 201 命中「缺少必填字段」规则 | 同上 |
| TCM-TRIAGE-004 | price 字符串仍 201 命中「类型错误」规则 | 同上 |
| TCM-TRIAGE-005 | price=0 仍 201 命中「边界值」规则 | 同上 |
| TCM-TRIAGE-006 | name 超 40 字符仍 201 命中「超长」规则 | 同上 |
| TCM-TRIAGE-007 | 种子数据 price 为字符串命中「种子数据类型」规则 | 同上 |
| TCM-TRIAGE-008 | 重名重复创建命中「重名」规则 | 同上 |
| TCM-TRIAGE-009 | 7 类失败同时出现按规则分组输出 | 输出含全部 7 组标题，并标注「未调用真实模型」 |
| TCM-TRIAGE-010 | 无失败用例 | 返回无需归因说明，不抛异常 |

### 二、种子数据（TCM-SEED）

| 编号 | 用例 | 预期 |
| --- | --- | --- |
| TCM-SEED-001 | 空库执行种子 | 创建「演示项目（SUT 8001）」，Base URL 为 http://127.0.0.1:8001，载入 3 个演示契约接口 |
| TCM-SEED-002 | 重复执行种子 | 幂等，不创建第二个项目 |
| TCM-SEED-003 | 登录后通过 API 查看 | 项目列表可见种子项目，endpointCount=3 |
| TCM-SEED-004 | ZHITEST_SEED_DEMO=false | 不创建种子项目 |

### 三、demo/sut 联调（TCM-SUT）

| 编号 | 用例 | 预期（bug 可复现） |
| --- | --- | --- |
| TCM-SUT-001 | GET 未知商品 | 返回 200 而非契约声明的 404 |
| TCM-SUT-002 | POST 缺少 name | 仍返回 201 |
| TCM-SUT-003 | POST price 为字符串 | 返回 201 且原样保存 |
| TCM-SUT-004 | POST price=0 | 返回 201（契约最小值 0.01） |
| TCM-SUT-005 | POST name 超 40 字符 | 返回 201 |
| TCM-SUT-006 | GET p-1 预置商品 | price 为字符串 "12.5" |
| TCM-SUT-007 | 相同 name 创建两次 | 两次都返回 201，列表出现重名 |
| TCM-SUT-008 | 联调端口约定 | main.py 启动端口为 8001 |

## 与仓库既有测试的关系

- 仓库既有 62 条 pytest 在 `zhitest/backend/tests/`，本目录不修改它们。
- 本目录测试复用后端代码与 `zhitest_test` 测试库，运行方式一致（后端 venv + 迁移到 head）。
- E2E 联调（真实 Worker 打真实 8001 SUT，验证报告 aiStatus=mock 且 7 类规则生效）见 `docs/项目解释与运行文档.md` 第 13 节。
