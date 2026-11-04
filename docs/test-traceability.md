# 测试追踪

`测试用例及跟踪(2).xlsx` 有 126 条用例，编号 TC-PROJECT-001 到 TC-CONFIG-014。自动化测试没有覆盖全部 126 条，也没有把手工步骤标成通过。

| 自动化测试 | 对应表格用例 | 覆盖范围 |
| --- | --- | --- |
| `tests/test_projects.py::test_create_list_and_detail` | TC-PROJECT-001 | 仅 API 创建成功。没有浏览器跳转到概览的断言。 |
| `tests/test_projects.py::test_duplicate_name_same_owner_conflict_and_other_owner_allowed` | TC-PROJECT-002 | 同一账号重名 409，列表数量不增加。 |
| `tests/test_projects.py::test_base_url_validation` | TC-PROJECT-003 | 空白、非法格式、内嵌口令。 |
| `tests/test_projects.py::test_empty_project_list` | TC-PROJECT-008 | API 返回空列表。空状态页面需浏览器查看。 |
| `tests/test_auth.py::test_expired_session_is_rejected` 与 `test_session_ttl_setting_matches_team_case` | TC-CONFIG-008 | 过期会话被拒绝，配置为 7200 秒。没有等待两小时。 |
| `tests/test_auth.py` 未登录与 `test_member_admin_status_is_forbidden` | TC-CONFIG-009 | 未登录 401；成员访问管理员状态 403。没有只读角色执行/删除场景。 |
| `tests/test_projects.py` 审计断言、`tests/test_auth.py` 登录审计 | TC-CONFIG-010 | 登录和创建项目写入审计。删除项目、模型配置、批量删除、权限变更功能不存在，未测。 |

其余 TC-IMPORT、TC-TESTGEN、TC-REVIEW、TC-TESTRUN、TC-BUG、TC-REPORT、TC-NOTIFY、TC-CONFIG 其余条目都没有自动化测试。

另外还有不在 126 条里、但属于 Phase 1 验收的测试：健康检查、requestId、口令不明文、跨项目 404、工作台空通过率、500 不泄露内部信息。
