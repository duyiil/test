"""「测试资产」模块接口自动化测试。

对应材料
--------
- ``资产测试模块拆分.docx``：页面/表单拆解、后端接口预留清单、核心业务逻辑与避坑指南。
- ``测试用例及跟踪(2).xlsx``：TC-IMPORT-001 ~ TC-IMPORT-014（被测对象接入）。
- ``敏捷开发Sprint追踪表_第二组_V4.xlsx``：AC-01 归属校验、AC-02 预览与确认、AC-03 重导入差异与版本、
  FR-API-01 导入限制/用例绑定、FR-SRC-01 源码 ZIP 安全隔离。
- 前端原型截图：``HTTP API 3 / Python 源码`` 两个 Tab、``POST /auth/login``、``POST /items``、
  ``GET /items/{{itemId}}``、``生成测试用例``、``+ 导入测试资产``。

本文件分两组
------------
A. **已实现功能**（普通用例，应当全部通过）：走后端真实接口
   ``/openapi/preview``、``/openapi/confirm``、``/endpoints``、``/generation-tasks``、
   ``/case-versions/{id}/submit|approve``、``/projects/{id}/archive``、``/projects/{id}/runs``。
B. **契约验收缺口**（``TestAssetAcceptanceGaps``，整组 ``xfail(strict=False)``）：
   按拆分文档里的预留契约与业务规则写出「期望行为」。当前后端尚未实现这些接口/校验，
   因此记为 xfailed 而不是让套件变红；后端补齐后会自动变成 XPASS（不算失败），
   届时可删除类上的 xfail 标记。若希望补齐后强制提醒清理标记，把 ``strict`` 改成 ``True``。

运行
----
需要 PostgreSQL 测试库（连接串见 ``tests/conftest.py``），先执行 ``alembic upgrade head``：

    cd zhitest/backend
    pytest tests/test_assets.py -q
    pytest tests/test_assets.py -q -rxX     # 同时列出每个 xfail 的具体原因

注意：现有的 ``tests/test_platform.py::test_openapi_preview_and_confirm_generates_drafts``
只覆盖了主链路；本文件补齐资产列表、预览/确认两阶段、版本管理、差异停用、待复核、
归档、越权、审计与导入边界，并单独把「文档要求但代码没做」的部分显式列为验收缺口。
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.testing import ApiEndpoint
from app.models.testing import TestCaseVersion as CaseVersion
from app.models.user import User
from app.modules.ai.openapi_parser import parse_openapi_document
from app.modules.testing.service import process_generation_task
from tests.helpers import login

API = "/api/v1"

# 与前端截图保持一致的「单品服务·接口定义」：3 个接口、1 个导入版本。
CONTRACT_V1: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "单品服务·接口定义", "version": "1.0.0"},
    "servers": [{"url": "http://127.0.0.1:9000"}],
    "paths": {
        "/auth/login": {
            "post": {
                "summary": "登录并获取访问凭证",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["username", "password"],
                                "properties": {
                                    "username": {"type": "string", "minLength": 1},
                                    "password": {"type": "string", "minLength": 8},
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"token": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "401": {"description": "unauthorized"},
                },
            }
        },
        "/items": {
            "post": {
                "summary": "创建商品并返回 ID",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["name", "price"],
                                "properties": {
                                    "name": {"type": "string", "maxLength": 64},
                                    "price": {"type": "number", "minimum": 0},
                                },
                            }
                        }
                    }
                },
                "responses": {
                    "201": {
                        "description": "created",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"id": {"type": "integer"}},
                                }
                            }
                        },
                    }
                },
            }
        },
        "/items/{itemId}": {
            "parameters": [
                {
                    "name": "itemId",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                    "example": "IT-001",
                }
            ],
            "get": {
                "summary": "查询商品详情检查类型",
                "parameters": [
                    {"name": "verbose", "in": "query", "schema": {"type": "boolean"}}
                ],
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "price": {"type": "number"},
                                    },
                                }
                            }
                        },
                    },
                    "404": {"description": "not found"},
                },
            },
        },
    },
}

# 同一组 (method, path)，但契约内容变化：用于验证「不覆盖、生成新版本」。
CONTRACT_V2: dict[str, Any] = {
    **{key: value for key, value in CONTRACT_V1.items() if key != "paths"},
    "info": {"title": "单品服务·接口定义", "version": "2.0.0"},
    "paths": {
        "/auth/login": CONTRACT_V1["paths"]["/auth/login"],
        "/items": {
            "post": {
                "summary": "创建商品并返回 ID（v2 增加库存字段）",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["name", "price", "stock"],
                                "properties": {
                                    "name": {"type": "string", "maxLength": 64},
                                    "price": {"type": "number", "minimum": 0},
                                    "stock": {"type": "integer", "minimum": 0},
                                },
                            }
                        }
                    }
                },
                "responses": {"201": {"description": "created"}},
            }
        },
        "/items/{itemId}": CONTRACT_V1["paths"]["/items/{itemId}"],
    },
}

# 少了 GET /items/{itemId}：用于验证「缺失项标记停用，不自动删除」。
CONTRACT_MISSING_ONE: dict[str, Any] = {
    **{key: value for key, value in CONTRACT_V1.items() if key != "paths"},
    "paths": {key: value for key, value in CONTRACT_V1["paths"].items() if key != "/items/{itemId}"},
}

# 预览必须具体报错而不是静默丢弃：一个坏 $ref、一个循环引用、一个正常接口。
CONTRACT_WITH_BAD_REFS: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "bad refs", "version": "1"},
    "components": {
        "schemas": {
            "Loop": {
                "type": "object",
                "properties": {"self": {"$ref": "#/components/schemas/Loop"}},
            }
        }
    },
    "paths": {
        "/health": {"get": {"summary": "健康检查", "responses": {"200": {"description": "ok"}}}},
        "/broken/ref": {
            "get": {
                "summary": "引用不存在的参数",
                "parameters": [{"$ref": "#/components/parameters/Missing"}],
                "responses": {"200": {"description": "ok"}},
            }
        },
        "/broken/loop": {
            "post": {
                "summary": "循环引用请求体",
                "requestBody": {
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Loop"}}
                    }
                },
                "responses": {"200": {"description": "ok"}},
            }
        },
    },
}

# 需求要求「不支持的结构要具体指出」：XML body 与 HEAD 方法目前会被悄悄忽略。
CONTRACT_WITH_UNSUPPORTED: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "unsupported", "version": "1"},
    "paths": {
        "/legacy/xml": {
            "post": {
                "summary": "仅支持 XML 请求体",
                "requestBody": {
                    "content": {"application/xml": {"schema": {"type": "string"}}}
                },
                "responses": {"200": {"description": "ok"}},
            },
            "head": {"summary": "不受支持的 HEAD 方法", "responses": {"200": {"description": "ok"}}},
        }
    },
}

SWAGGER_2_DOCUMENT: dict[str, Any] = {
    "swagger": "2.0",
    "info": {"title": "legacy", "version": "1"},
    "paths": {"/items": {"get": {"summary": "列表", "responses": {"200": {"description": "ok"}}}}},
}


# --------------------------------------------------------------------------- #
# 公共辅助
# --------------------------------------------------------------------------- #
def _yaml(document: dict[str, Any]) -> str:
    return yaml.safe_dump(document, allow_unicode=True, sort_keys=False)


def _json(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False)


def _project(client: TestClient, name: str = "资产测试项目") -> str:
    assert login(client).status_code == 200
    created = client.post(
        f"{API}/projects",
        json={
            "name": name,
            "description": "测试资产模块自动化用例",
            "baseUrl": "http://127.0.0.1:9000",
            "envLabel": "测试",
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"]


def _preview(client: TestClient, project_id: str, raw: str):
    return client.post(f"{API}/projects/{project_id}/openapi/preview", json={"document": raw})


def _confirm(client: TestClient, project_id: str, raw: str):
    return client.post(f"{API}/projects/{project_id}/openapi/confirm", json={"document": raw})


def _endpoints(client: TestClient, project_id: str) -> list[dict[str, Any]]:
    response = client.get(f"{API}/projects/{project_id}/endpoints")
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


def _import_v1(client: TestClient, project_id: str) -> dict[str, Any]:
    response = _confirm(client, project_id, _yaml(CONTRACT_V1))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _cases(client: TestClient, project_id: str, review_status: str | None = None) -> list[dict[str, Any]]:
    params = {"reviewStatus": review_status} if review_status else None
    response = client.get(f"{API}/projects/{project_id}/cases", params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


def _approve(client: TestClient, version_id: str) -> None:
    submitted = client.post(f"{API}/case-versions/{version_id}/submit")
    assert submitted.status_code == 200, submitted.text
    approved = client.post(f"{API}/case-versions/{version_id}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["reviewStatus"] == "confirmed"


def _generate(client: TestClient, db_session: Session, project_id: str) -> dict[str, Any]:
    created = client.post(f"{API}/projects/{project_id}/generation-tasks")
    assert created.status_code == 202, created.text
    task_id = created.json()["data"]["id"]
    process_generation_task(db_session, uuid.UUID(task_id))
    db_session.expire_all()
    detail = client.get(f"{API}/generation-tasks/{task_id}")
    assert detail.status_code == 200, detail.text
    return detail.json()["data"]


def _zip_bytes(entries: dict[str, str], symlink: str | None = None) -> bytes:
    """构造内存 ZIP；symlink 用 Unix 外部属性标记为符号链接。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            archive.writestr(info, "/etc/passwd")
    return buffer.getvalue()


def _bulk_document(count: int) -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {"title": "bulk", "version": "1"},
        "paths": {
            f"/bulk/{index}": {
                "get": {"summary": f"bulk-{index}", "responses": {"200": {"description": "ok"}}}
            }
            for index in range(count)
        },
    }


# --------------------------------------------------------------------------- #
# A. 已实现功能：应当全部通过
# --------------------------------------------------------------------------- #
def test_asset_list_empty_then_populated_after_import(client: TestClient) -> None:
    """TC-IMPORT-001/002/004：未导入显示空列表；确认导入后清单含方法、路径、名称、版本。"""
    project_id = _project(client)

    assert _endpoints(client, project_id) == []

    preview = _preview(client, project_id, _yaml(CONTRACT_V1))
    assert preview.status_code == 200, preview.text
    parsed = preview.json()["data"]
    assert parsed["openapi"] == "3.0.3"
    assert len(parsed["endpoints"]) == 3
    assert {(item["method"], item["path"]) for item in parsed["endpoints"]} == {
        ("POST", "/auth/login"),
        ("POST", "/items"),
        ("GET", "/items/{itemId}"),
    }

    saved = _import_v1(client, project_id)
    assert saved == {"saved": 3, "disabled": 0, "errors": []}

    items = _endpoints(client, project_id)
    assert len(items) == 3
    assert all(item["specVersion"] == 1 for item in items)
    assert all(item["projectId"] == project_id for item in items)
    assert all({"id", "method", "path", "summary", "specVersion", "createdAt"} <= set(item) for item in items)
    assert len({item["id"] for item in items}) == 3
    by_path = {item["path"]: item for item in items}
    assert by_path["/items"]["summary"] == "创建商品并返回 ID"
    assert by_path["/items/{itemId}"]["method"] == "GET"

    # 项目概览/列表的接口数由同一张资产表统计。
    detail = client.get(f"{API}/projects/{project_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["endpointCount"] == 3


def test_preview_is_readonly_and_never_persists(client: TestClient, db_session: Session) -> None:
    """AC-02：预览与确认是两阶段，预览阶段不得落库、不得写确认审计。"""
    project_id = _project(client)
    assert _preview(client, project_id, _yaml(CONTRACT_V1)).status_code == 200

    count = db_session.scalar(
        select(func.count()).select_from(ApiEndpoint).where(ApiEndpoint.project_id == uuid.UUID(project_id))
    )
    assert count == 0
    assert _endpoints(client, project_id) == []
    audit = db_session.scalar(select(AuditLog).where(AuditLog.action == "openapi.confirm"))
    assert audit is None

    _import_v1(client, project_id)
    db_session.expire_all()
    count = db_session.scalar(
        select(func.count()).select_from(ApiEndpoint).where(ApiEndpoint.project_id == uuid.UUID(project_id))
    )
    assert count == 3


def test_preview_accepts_json_and_yaml_with_identical_result(client: TestClient) -> None:
    """TC-IMPORT-002：JSON / YAML 两种格式的解析结果必须一致。"""
    project_id = _project(client)
    from_yaml = _preview(client, project_id, _yaml(CONTRACT_V1)).json()["data"]
    from_json = _preview(client, project_id, _json(CONTRACT_V1)).json()["data"]
    assert from_yaml == from_json

    # 纯解析单元：不经过 HTTP，便于定位格式差异。
    assert parse_openapi_document(_yaml(CONTRACT_V1)) == parse_openapi_document(_json(CONTRACT_V1))


def test_preview_preserves_parameters_body_and_responses(client: TestClient) -> None:
    """TC-IMPORT-001 / 需求 2.2：参数位置、类型、必填、约束与响应结构不得丢失。"""
    project_id = _project(client)
    parsed = _preview(client, project_id, _yaml(CONTRACT_V1))
    assert parsed.status_code == 200
    endpoints = {item["path"]: item for item in parsed.json()["data"]["endpoints"]}

    login_ep = endpoints["/auth/login"]
    assert login_ep["summary"] == "登录并获取访问凭证"
    assert login_ep["body"]["type"] == "object"
    assert set(login_ep["body"]["required"]) == {"username", "password"}
    assert login_ep["body"]["properties"]["password"]["minLength"] == 8
    assert set(login_ep["responses"]) == {"200", "401"}

    create_ep = endpoints["/items"]
    assert create_ep["body"]["properties"]["price"]["minimum"] == 0
    assert create_ep["body"]["properties"]["name"]["maxLength"] == 64

    detail_ep = endpoints["/items/{itemId}"]
    assert detail_ep["query"] == [{"name": "verbose", "type": "boolean", "required": False}]
    assert detail_ep["pathParams"][0]["name"] == "itemId"
    assert detail_ep["pathParams"][0]["required"] is True
    assert detail_ep["pathParams"][0]["example"] == "IT-001"
    assert detail_ep["responses"]["200"]["properties"]["price"]["type"] == "number"
    assert parsed.json()["data"]["warnings"] == []


@pytest.mark.parametrize(
    ("raw", "keyword"),
    [
        (_yaml(SWAGGER_2_DOCUMENT), "OpenAPI 3.x"),
        (_json({"hello": "world"}), "OpenAPI 3.x"),
        ("   ", "文档为空"),
        ("一份普通说明文本，不是接口文档", "OpenAPI 文档必须是对象"),
        ("这不是一份接口文档 ::: [", "既不是 JSON 也不是 YAML"),
    ],
)
def test_preview_rejects_non_openapi_document_with_actionable_reason(
    client: TestClient, raw: str, keyword: str
) -> None:
    """TC-IMPORT-005：非 OpenAPI 文档要给出可操作原因，而不是笼统的「导入失败」。"""
    project_id = _project(client)
    response = _preview(client, project_id, raw)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert keyword in body["message"], body["message"]


def test_preview_reports_bad_refs_instead_of_dropping(client: TestClient) -> None:
    """需求分析 3.1 / AC-02：不支持或错误的结构必须定位到字段，不静默丢弃。"""
    project_id = _project(client)
    response = _preview(client, project_id, _yaml(CONTRACT_WITH_BAD_REFS))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [item["path"] for item in data["endpoints"]] == ["/health"]
    assert len(data["errors"]) == 2
    assert all({"loc", "msg"} <= set(error) for error in data["errors"])
    messages = " ".join(error["msg"] for error in data["errors"])
    assert "引用不存在" in messages
    assert "循环引用" in messages
    assert any(error["loc"].startswith("paths.") for error in data["errors"])

    # 确认导入同样把错误带出来，供前端展示「解析出 X 个接口 / 不支持的结构」。
    confirmed = _confirm(client, project_id, _yaml(CONTRACT_WITH_BAD_REFS))
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["errors"] == data["errors"]


def test_single_import_limit_is_300_endpoints(client: TestClient) -> None:
    """TC-IMPORT-007 / FR-API-01：单次 300 个接口为上限，超过要提示分批且不导入。"""
    project_id = _project(client)

    too_many = _preview(client, project_id, _json(_bulk_document(301)))
    assert too_many.status_code == 422
    assert "300" in too_many.json()["message"]
    assert _endpoints(client, project_id) == []

    exactly = _preview(client, project_id, _json(_bulk_document(300)))
    assert exactly.status_code == 200, exactly.text
    assert len(exactly.json()["data"]["endpoints"]) == 300
    assert _endpoints(client, project_id) == []  # 预览依旧不落库


def test_reimport_same_method_path_creates_new_version_not_overwrite(
    client: TestClient, db_session: Session
) -> None:
    """TC-IMPORT-008/009 / AC-03：相同 Method+Path 再次导入形成新版本，不覆盖历史。"""
    project_id = _project(client)
    _import_v1(client, project_id)
    before = {item["path"]: item for item in _endpoints(client, project_id)}
    contract_before = db_session.scalar(
        select(ApiEndpoint.contract).where(ApiEndpoint.id == uuid.UUID(before["/items"]["id"]))
    )

    changed = _confirm(client, project_id, _yaml(CONTRACT_V2))
    assert changed.status_code == 200, changed.text
    assert changed.json()["data"]["saved"] == 3
    assert changed.json()["data"]["disabled"] == 0

    after = {item["path"]: item for item in _endpoints(client, project_id)}
    assert set(after) == set(before)
    assert all(after[path]["id"] == before[path]["id"] for path in before), "同接口应复用同一资产行"
    assert after["/items"]["specVersion"] == before["/items"]["specVersion"] + 1 == 2
    assert after["/items"]["summary"] == "创建商品并返回 ID（v2 增加库存字段）"

    total = db_session.scalar(
        select(func.count()).select_from(ApiEndpoint).where(ApiEndpoint.project_id == uuid.UUID(project_id))
    )
    assert total == 3, "不得因重导入产生重复资产行"
    db_session.expire_all()
    contract_after = db_session.scalar(
        select(ApiEndpoint.contract).where(ApiEndpoint.id == uuid.UUID(before["/items"]["id"]))
    )
    assert contract_after["body"]["properties"].get("stock") is not None
    assert contract_before["body"]["properties"].get("stock") is None


def test_reimport_marks_missing_endpoints_disabled(client: TestClient, db_session: Session) -> None:
    """TC-IMPORT-008：缺失接口只标记停用，不自动删除；停用接口不再进入生成任务。"""
    project_id = _project(client)
    _import_v1(client, project_id)

    reduced = _confirm(client, project_id, _yaml(CONTRACT_MISSING_ONE))
    assert reduced.status_code == 200, reduced.text
    assert reduced.json()["data"]["saved"] == 2
    assert reduced.json()["data"]["disabled"] == 1

    db_session.expire_all()
    rows = db_session.scalars(
        select(ApiEndpoint).where(ApiEndpoint.project_id == uuid.UUID(project_id))
    ).all()
    assert len(rows) == 3, "历史资产行必须保留，供旧报告回溯"
    missing = next(row for row in rows if row.path == "/items/{itemId}")
    assert missing.disabled is True
    assert all(row.disabled is False for row in rows if row.id != missing.id)

    task = client.post(f"{API}/projects/{project_id}/generation-tasks")
    assert task.status_code == 202, task.text
    task_id = task.json()["data"]["id"]
    # 创建响应的 GenerationTarget 尚未 flush；按拆分文档的「轮询任务状态」读取详情。
    detail = client.get(f"{API}/generation-tasks/{task_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["targetCount"] == 2, "停用接口不得参与新一轮用例生成"


def test_reimport_marks_confirmed_cases_pending_review_and_blocks_execution(
    client: TestClient, db_session: Session
) -> None:
    """TC-IMPORT-009 / FR-API-01：契约变更 → 已确认用例转待复核，历史版本保留且禁止新执行。"""
    project_id = _project(client)
    _import_v1(client, project_id)
    generated = _generate(client, db_session, project_id)
    assert generated["status"] == "succeeded"
    assert generated["succeededCount"] == generated["targetCount"] == 3

    drafts = _cases(client, project_id, "draft")
    assert drafts
    chosen = drafts[:2]
    for item in chosen:
        _approve(client, item["id"])
    assert len(_cases(client, project_id, "confirmed")) == 2

    changed = _confirm(client, project_id, _yaml(CONTRACT_V2))
    assert changed.status_code == 200, changed.text

    for item in chosen:
        detail = client.get(f"{API}/case-versions/{item['id']}")
        assert detail.status_code == 200, detail.text
        payload = detail.json()["data"]
        # 旧版本 id 仍可访问、内容不变；最新实例已经是待复核的新版本。
        assert payload["reviewStatus"] == "confirmed"
        assert payload["specVersion"] == 1
        cases = client.get(f"{API}/projects/{project_id}/cases").json()["data"]["items"]
        latest = next(case for case in cases if case["caseId"] == item["caseId"])
        assert latest["versionNumber"] == 2
        assert latest["specVersion"] == 2
        assert latest["reviewStatus"] == "pending_review"
        assert "接口契约已更新" in latest["basis"]
        history = {entry["versionNumber"]: entry["reviewStatus"] for entry in latest["history"]}
        assert history[1] == "confirmed", "历史执行指向的旧版本不能被覆盖"

    # 待复核用例不可执行：服务端执行门槛必须拒绝，而不是只靠前端置灰。
    run = client.post(f"{API}/projects/{project_id}/runs", json={"confirmWrites": True})
    assert run.status_code == 422, run.text
    assert "没有已确认且带断言的用例可执行" in run.json()["message"]

    db_session.expire_all()
    confirmed_versions = db_session.scalar(
        select(func.count())
        .select_from(CaseVersion)
        .where(CaseVersion.review_status == "confirmed")
    )
    assert confirmed_versions == 2, "旧版本应完整保留，只是不再作为最新可执行版本"


def test_generation_task_requires_contract_and_returns_async_task(
    client: TestClient, db_session: Session
) -> None:
    """TC-TESTGEN-001：无资产不能生成；有资产时返回异步任务 ID 与每个接口的目标。"""
    project_id = _project(client)

    empty = client.post(f"{API}/projects/{project_id}/generation-tasks")
    assert empty.status_code == 422
    assert "接口契约" in empty.json()["message"]

    _import_v1(client, project_id)
    created = client.post(f"{API}/projects/{project_id}/generation-tasks")
    assert created.status_code == 202, created.text
    task = created.json()["data"]
    assert task["status"] == "queued"
    assert task["id"]

    # 任务目标在提交后才可见，进度以 GET 详情为准（对应拆分文档的轮询设计）。
    polled = client.get(f"{API}/generation-tasks/{task['id']}")
    assert polled.status_code == 200, polled.text
    detail = polled.json()["data"]
    assert detail["id"] == task["id"]
    assert detail["targetCount"] == 3
    assert len(detail["targets"]) == 3
    assert all(target["status"] == "queued" for target in detail["targets"])

    endpoint_ids = {item["id"] for item in _endpoints(client, project_id)}
    assert {target["endpointId"] for target in detail["targets"]} == endpoint_ids


def test_generation_produces_drafts_that_cannot_be_executed(
    client: TestClient, db_session: Session
) -> None:
    """TC-TESTGEN-001/006：生成结果一律是草稿态，带断言，且不能直接触发执行。"""
    project_id = _project(client)
    _import_v1(client, project_id)
    task = _generate(client, db_session, project_id)
    assert task["status"] == "succeeded"
    assert task["succeededCount"] == 3
    assert task["failedCount"] == 0

    all_cases = _cases(client, project_id)
    assert all_cases
    assert all(case["reviewStatus"] == "draft" for case in all_cases)
    assert all(case["assertions"] for case in all_cases), "每条草稿必须含请求构造与断言规则"
    assert all(case["specVersion"] == 1 for case in all_cases)
    paths = {case["relativePath"] for case in all_cases}
    assert paths <= {"/auth/login", "/items", "/items/{itemId}"}

    run = client.post(f"{API}/projects/{project_id}/runs", json={"confirmWrites": True})
    assert run.status_code == 422, run.text
    assert "没有已确认且带断言的用例可执行" in run.json()["message"]


def test_assets_are_scoped_to_project_owner(client: TestClient, db_session: Session) -> None:
    """AC-01 / TC-CONFIG-009：跨账号访问他人资产返回 404，不泄露资源是否存在。"""
    project_id = _project(client)
    _import_v1(client, project_id)

    now = datetime.now(timezone.utc)
    db_session.add(
        User(
            username="asset_other",
            password_hash=hash_password("Member_Pass_123"),
            display_name="其他账号",
            role="member",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    assert login(client, "asset_other", "Member_Pass_123").status_code == 200

    assert client.get(f"{API}/projects/{project_id}/endpoints").status_code == 404
    assert _preview(client, project_id, _yaml(CONTRACT_V1)).status_code == 404
    assert _confirm(client, project_id, _yaml(CONTRACT_V1)).status_code == 404
    assert client.post(f"{API}/projects/{project_id}/generation-tasks").status_code == 404
    assert client.get(f"{API}/projects/{project_id}/endpoints").json()["code"] == "NOT_FOUND"


def test_confirm_import_writes_audit_log(client: TestClient, db_session: Session) -> None:
    """TC-CONFIG-010：资产导入属于敏感操作，必须记录操作人、项目与导入结果。"""
    project_id = _project(client)
    _import_v1(client, project_id)

    db_session.expire_all()
    logs = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "openapi.confirm").order_by(AuditLog.created_at)
    ).all()
    assert len(logs) == 1
    assert logs[0].resource_type == "project"
    assert logs[0].resource_id == project_id
    assert logs[0].actor_id is not None
    assert logs[0].detail == {"saved": 3, "disabled": 0, "errors": 0}


def test_archived_project_assets_are_readonly_for_execution(
    client: TestClient, db_session: Session
) -> None:
    """TC-PROJECT-010：归档项目只读查看资产，但服务端必须拒绝触发执行。"""
    project_id = _project(client)
    _import_v1(client, project_id)
    _generate(client, db_session, project_id)
    first = _cases(client, project_id, "draft")[0]
    _approve(client, first["id"])

    archived = client.post(f"{API}/projects/{project_id}/archive")
    assert archived.status_code == 200, archived.text
    assert archived.json()["data"]["status"] == "archived"

    assert len(_endpoints(client, project_id)) == 3, "归档后仍可只读查看接口清单"
    run = client.post(f"{API}/projects/{project_id}/runs", json={"confirmWrites": True})
    assert run.status_code == 409, run.text
    assert run.json()["code"] == "ARCHIVED"
    assert "归档" in run.json()["message"]


# --------------------------------------------------------------------------- #
# B. 契约验收缺口：按拆分文档写期望，当前实现未覆盖，统一 xfail
# --------------------------------------------------------------------------- #
@pytest.mark.xfail(
    reason="资产测试模块拆分.docx 的预留契约 / 业务规则尚未实现；后端补齐后本组应转为 XPASS",
    strict=False,
)
class TestAssetAcceptanceGaps:
    """Sprint 2/3 待验收项。当前后端只有 /openapi/* 与 /endpoints，没有 /assets/* 路由。"""

    @pytest.mark.parametrize(
        ("path", "required_fields"),
        [
            ("assets/api", {"id", "method", "path", "name", "version", "status"}),
            ("assets/source", {"snapshotId", "fileName", "targetCount", "status"}),
        ],
    )
    def test_reserved_asset_list_routes(self, client: TestClient, path: str, required_fields: set[str]) -> None:
        """拆分文档「后端接口预留清单」：HTTP API / Python 源码 两类资产各有列表接口。"""
        project_id = _project(client)
        response = client.get(f"{API}/projects/{project_id}/{path}")
        assert response.status_code == 200, response.text
        items = response.json()["data"]["items"]
        assert all(required_fields <= set(item) for item in items)

    def test_reserved_api_asset_detail_route(self, client: TestClient) -> None:
        """GET /assets/api/{apiId}：返回 headers / reqBody / responses 完整定义。"""
        project_id = _project(client)
        _import_v1(client, project_id)
        api_id = _endpoints(client, project_id)[0]["id"]
        response = client.get(f"{API}/projects/{project_id}/assets/api/{api_id}")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert {"id", "method", "path", "headers", "reqBody", "responses"} <= set(data)

    def test_reserved_preview_and_import_routes_with_conflict_strategy(self, client: TestClient) -> None:
        """POST /assets/api/preview + /assets/api/import：预览计数、invalidFields、冲突策略。"""
        project_id = _project(client)
        preview = client.post(
            f"{API}/projects/{project_id}/assets/api/preview",
            json={"content": _json(CONTRACT_V1)},
        )
        assert preview.status_code == 200, preview.text
        preview_data = preview.json()["data"]
        assert preview_data["success"] is True
        assert preview_data["interfaceCount"] == 3
        assert "invalidFields" in preview_data

        imported = client.post(
            f"{API}/projects/{project_id}/assets/api/import",
            json={"parsedData": preview_data, "conflictStrategy": "new_version"},
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["data"] == {"success": True, "importedCount": 3}

    def test_reserved_source_zip_upload_and_file_tree(self, client: TestClient) -> None:
        """FR-SRC-01 / Sprint 2：ZIP 上传预览返回快照与安全过滤结果，文件树可查。"""
        project_id = _project(client)
        payload = _zip_bytes(
            {
                "src/discount.py": "def discount(price, rate):\n    return price * rate\n",
                ".env": "SECRET=should-not-be-analyzed\n",
                ".venv/lib/placeholder.py": "pass\n",
            }
        )
        uploaded = client.post(
            f"{API}/projects/{project_id}/assets/source/upload",
            files={"file": ("source.zip", payload, "application/zip")},
        )
        assert uploaded.status_code == 200, uploaded.text
        data = uploaded.json()["data"]
        assert "snapshotId" in data and "securityCheck" in data
        excluded = " ".join(str(item) for item in data["excluded"])
        assert ".env" in excluded and ".venv" in excluded

        snapshot_id = data["snapshotId"]
        tree = client.get(f"{API}/projects/{project_id}/assets/source/{snapshot_id}")
        assert tree.status_code == 200, tree.text
        tree_data = tree.json()["data"]
        assert tree_data["snapshotId"] == snapshot_id
        assert "src/discount.py" in str(tree_data["fileTree"])
        assert "excludedFiles" in tree_data

    def test_source_zip_path_traversal_and_symlink_are_rejected(self, client: TestClient) -> None:
        """FR-SRC-01：路径穿越、绝对路径、软链接必须拒绝，且解析不得执行用户代码。"""
        project_id = _project(client)
        payload = _zip_bytes(
            {
                "../evil.py": "print('escaped')\n",
                "/tmp/absolute.py": "print('absolute')\n",
                "src/ok.py": "def ok():\n    return 1\n",
            },
            symlink="src/link.py",
        )
        response = client.post(
            f"{API}/projects/{project_id}/assets/source/upload",
            files={"file": ("dangerous.zip", payload, "application/zip")},
        )
        assert response.status_code == 422, response.text
        message = response.json()["message"]
        assert any(keyword in message for keyword in ("路径穿越", "绝对路径", "软链接")), message
        listing = client.get(f"{API}/projects/{project_id}/assets/source")
        assert listing.status_code == 200
        assert listing.json()["data"]["items"] == [], "非法 ZIP 不得形成快照"

    @pytest.mark.parametrize(
        ("kind", "body"),
        [
            ("api", None),
            ("source", {"targetFunctions": ["discount"]}),
        ],
    )
    def test_reserved_generate_routes_return_task_id(
        self, client: TestClient, kind: str, body: dict[str, Any] | None
    ) -> None:
        """拆分文档：单接口生成测试草稿 / 源码生成 pytest 草稿，均返回异步 taskId。"""
        project_id = _project(client)
        if kind == "api":
            _import_v1(client, project_id)
            api_id = _endpoints(client, project_id)[0]["id"]
            url = f"{API}/projects/{project_id}/assets/api/{api_id}/generate"
        else:
            payload = _zip_bytes({"src/discount.py": "def discount(price, rate):\n    return price * rate\n"})
            uploaded = client.post(
                f"{API}/projects/{project_id}/assets/source/upload",
                files={"file": ("source.zip", payload, "application/zip")},
            )
            assert uploaded.status_code == 200, uploaded.text
            url = f"{API}/projects/{project_id}/assets/source/{uploaded.json()['data']['snapshotId']}/generate"
        response = client.post(url, json=body) if body else client.post(url)
        assert response.status_code in (200, 202), response.text
        assert response.json()["data"]["taskId"]

    def test_reserved_task_polling_exposes_progress(self, client: TestClient) -> None:
        """GET /tasks/{taskId}：前端轮询生成任务状态、进度与提示。"""
        project_id = _project(client)
        _import_v1(client, project_id)
        task_id = client.post(f"{API}/projects/{project_id}/generation-tasks").json()["data"]["id"]
        response = client.get(f"{API}/tasks/{task_id}")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert {"status", "progress", "msg"} <= set(data)

    def test_generation_create_response_reports_target_count(self, client: TestClient) -> None:
        """AC-19 / 拆分文档「生成任务进度」：创建任务时就应返回 N/M 的目标数。

        当前 ``SessionLocal(autoflush=False)`` 使 GenerationTarget 在响应序列化时还没写入，
        POST 响应恒为 targetCount=0，必须再发一次 GET 才拿得到；对前端进度展示不友好。
        """
        project_id = _project(client)
        _import_v1(client, project_id)
        created = client.post(f"{API}/projects/{project_id}/generation-tasks")
        assert created.status_code == 202, created.text
        assert created.json()["data"]["targetCount"] == 3
        assert len(created.json()["data"]["targets"]) == 3

    def test_archived_project_rejects_import_and_generation(self, client: TestClient) -> None:
        """需求第 10 章：归档项目前端置灰后，后端必须对导入与生成做强校验并拒绝。"""
        project_id = _project(client)
        _import_v1(client, project_id)
        assert client.post(f"{API}/projects/{project_id}/archive").status_code == 200

        imported = _confirm(client, project_id, _yaml(CONTRACT_V2))
        assert imported.status_code == 409, imported.text
        assert imported.json()["code"] == "ARCHIVED"
        generated = client.post(f"{API}/projects/{project_id}/generation-tasks")
        assert generated.status_code == 409, generated.text
        assert generated.json()["code"] == "ARCHIVED"
        assert len(_endpoints(client, project_id)) == 3, "只读查看仍应可用"

    def test_unsupported_body_and_method_are_reported(self, client: TestClient) -> None:
        """需求分析 3.1：XML body 与不受支持的方法必须在预览里点名，不能悄悄忽略。"""
        project_id = _project(client)
        response = _preview(client, project_id, _yaml(CONTRACT_WITH_UNSUPPORTED))
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        reported = " ".join(
            str(item.get("msg", "")) for item in data["errors"] + data["warnings"]
        )
        assert "xml" in reported.lower(), reported
        assert "head" in reported.lower(), reported

    def test_swagger_2_document_is_supported(self, client: TestClient) -> None:
        """TC-IMPORT-003：需求要求兼容 Swagger 2.0；当前解析器明确只支持 3.x。"""
        project_id = _project(client)
        response = _preview(client, project_id, _yaml(SWAGGER_2_DOCUMENT))
        assert response.status_code == 200, response.text
        assert response.json()["data"]["endpoints"][0]["path"] == "/items"

    def test_missing_servers_prompts_base_url(self, client: TestClient) -> None:
        """TC-IMPORT-006：文档缺少 servers 时提示补充 Base URL 后方可导入。"""
        project_id = _project(client)
        document = {key: value for key, value in CONTRACT_V1.items() if key != "servers"}
        response = _preview(client, project_id, _yaml(document))
        assert response.status_code == 200, response.text
        warnings = " ".join(str(item.get("msg", "")) for item in response.json()["data"]["warnings"])
        assert "servers" in warnings.lower() or "Base URL" in warnings

    def test_preview_allows_selecting_endpoints_before_import(self, client: TestClient) -> None:
        """TC-IMPORT-004：导入前可勾选纳入范围，只导入选中的接口。"""
        project_id = _project(client)
        response = client.post(
            f"{API}/projects/{project_id}/openapi/confirm",
            json={"document": _yaml(CONTRACT_V1), "selected": ["/items"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["saved"] == 1
        assert [item["path"] for item in _endpoints(client, project_id)] == ["/items"]

    def test_manual_endpoint_entry_validates_required_fields(self, client: TestClient) -> None:
        """TC-IMPORT-010/011：无文档时可手工录入接口，路径/方法必填。"""
        project_id = _project(client)
        url = f"{API}/projects/{project_id}/endpoints"
        invalid = client.post(url, json={"path": "/api/v1/orders"})
        assert invalid.status_code == 422, invalid.text
        created = client.post(
            url,
            json={
                "method": "POST",
                "path": "/api/v1/orders",
                "headers": {"Content-Type": "application/json"},
                "reqBody": {"type": "object"},
                "responses": {"201": {"description": "created"}},
            },
        )
        assert created.status_code == 201, created.text
        assert any(item["path"] == "/api/v1/orders" for item in _endpoints(client, project_id))

    def test_endpoint_tags_filter_and_detail_stats(self, client: TestClient) -> None:
        """TC-IMPORT-013/014：标签筛选与接口详情（关联用例数、历史通过率）。"""
        project_id = _project(client)
        _import_v1(client, project_id)
        api_id = _endpoints(client, project_id)[0]["id"]
        tagged = client.post(
            f"{API}/projects/{project_id}/endpoints/{api_id}/tags",
            json={"tags": ["核心链路"], "group": "订单"},
        )
        assert tagged.status_code == 200, tagged.text
        filtered = client.get(f"{API}/projects/{project_id}/endpoints", params={"tag": "核心链路"})
        assert filtered.status_code == 200
        assert len(filtered.json()["data"]["items"]) == 1
        detail = client.get(f"{API}/projects/{project_id}/endpoints/{api_id}")
        assert detail.status_code == 200, detail.text
        assert {"caseCount", "passRate"} <= set(detail.json()["data"])

    def test_reimport_reports_added_changed_removed_diff(self, client: TestClient) -> None:
        """TC-IMPORT-008 / AC-03：重导入要给出新增/变更/删除的差异清单。"""
        project_id = _project(client)
        _import_v1(client, project_id)
        response = client.post(
            f"{API}/projects/{project_id}/openapi/preview",
            json={"document": _yaml(CONTRACT_V2)},
        )
        assert response.status_code == 200, response.text
        diff = response.json()["data"].get("diff")
        assert diff is not None, "预览需返回差异提示"
        assert {"added", "changed", "removed"} <= set(diff)
        assert len(diff["changed"]) >= 1

    def test_source_asset_uses_static_analysis_only(self, client: TestClient) -> None:
        """FR-SRC-01：静态 AST 分析输出可测函数，且明确标注未 import/执行用户模块。"""
        project_id = _project(client)
        payload = _zip_bytes(
            {"src/discount.py": "def discount(price, rate):\n    return price * rate\n"}
        )
        uploaded = client.post(
            f"{API}/projects/{project_id}/assets/source/upload",
            files={"file": ("source.zip", payload, "application/zip")},
        )
        assert uploaded.status_code == 200, uploaded.text
        data = uploaded.json()["data"]
        assert "discount" in str(data.get("targets", ""))
        assert data.get("analysisMode") == "static-ast"
        assert data.get("executed") is False
