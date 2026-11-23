"""US-03.2 用例版本保存：仅可执行内容变化才新增版本。"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from app.models.audit import AuditLog  # noqa: E402
from app.modules.testing.service import process_generation_task  # noqa: E402
from tests.helpers import login  # noqa: E402


def _project(client: TestClient, name: str) -> str:
    """创建项目并完成登录，返回项目 id。"""
    login(client)
    response = client.post(
        "/api/v1/projects",
        json={"name": name, "description": "edit-versioning", "baseUrl": "http://127.0.0.1:9000", "envLabel": "测试"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def _drafts(client: TestClient, project_id: str, db_session: Session) -> list[dict[str, Any]]:
    """载入演示契约并用确定性 Mock 生成器产出草稿用例。"""
    loaded = client.post(f"/api/v1/projects/{project_id}/contract/demo")
    assert loaded.status_code == 200, loaded.text
    created = client.post(f"/api/v1/projects/{project_id}/generation-tasks")
    assert created.status_code == 202, created.text
    task_id = uuid.UUID(created.json()["data"]["id"])
    process_generation_task(db_session, task_id)
    detail = client.get(f"/api/v1/generation-tasks/{task_id}")
    assert detail.json()["data"]["status"] == "succeeded"
    cases = client.get(f"/api/v1/projects/{project_id}/cases", params={"reviewStatus": "draft"})
    items = cases.json()["data"]["items"]
    assert items
    return items


def _confirm(client: TestClient, version_id: str) -> None:
    """提交并审核通过，得到一个 confirmed 版本。"""
    submitted = client.post(f"/api/v1/case-versions/{version_id}/submit")
    assert submitted.status_code == 200, submitted.text
    approved = client.post(f"/api/v1/case-versions/{version_id}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["reviewStatus"] == "confirmed"


def _edit(client: TestClient, version_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """调用编辑接口并返回 data 载荷。"""
    response = client.post(f"/api/v1/case-versions/{version_id}/edit", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _case(items: list[dict[str, Any]], *, method: str) -> dict[str, Any]:
    """按 method 查找用例，避免依赖数据库未排序的返回顺序。"""
    for item in items:
        if item["method"] == method:
            return item
    raise AssertionError(f"找不到 method={method} 的草稿用例")


def test_edit_description_only_keeps_version_and_status(client: TestClient, db_session: Session) -> None:
    """仅改 description：版本号、review_status 不变，写入 action=edit 的 ReviewEvent 与 metaOnly 审计。"""
    project_id = _project(client, "元信息编辑")
    items = _drafts(client, project_id, db_session)
    target = items[0]
    data = _edit(client, target["id"], {"description": "只改描述，不改任何可执行内容"})
    assert data["id"] == target["id"]
    assert data["versionNumber"] == target["versionNumber"]
    assert data["reviewStatus"] == target["reviewStatus"]
    assert data["description"] == "只改描述，不改任何可执行内容"
    assert data["events"][-1]["action"] == "edit"
    assert "不产生新版本" in data["events"][-1]["reason"]
    assert len(data["history"]) == 1
    db_session.expire_all()
    audits = list(db_session.scalars(select(AuditLog).where(AuditLog.action == "case.edit")).all())
    assert any(item.detail and item.detail.get("metaOnly") is True for item in audits)


def test_edit_name_on_confirmed_keeps_confirmed(client: TestClient, db_session: Session) -> None:
    """confirmed 版本仅改 name：仍是 confirmed、版本号不变、仍是同一版本 id。"""
    project_id = _project(client, "确认后改名")
    items = _drafts(client, project_id, db_session)
    target = items[0]
    _confirm(client, target["id"])
    data = _edit(client, target["id"], {"name": "确认后仅改名"})
    assert data["id"] == target["id"]
    assert data["versionNumber"] == target["versionNumber"]
    assert data["reviewStatus"] == "confirmed"
    assert data["name"] == "确认后仅改名"
    assert len(data["history"]) == 1


def test_edit_all_meta_fields_keeps_version(client: TestClient, db_session: Session) -> None:
    """同时改 name/description/scenario/basis：全部原地生效且不产生新版本。"""
    project_id = _project(client, "多字段元信息编辑")
    items = _drafts(client, project_id, db_session)
    target = items[0]
    data = _edit(
        client,
        target["id"],
        {
            "name": "新名称",
            "description": "新描述",
            "scenario": "回归验证",
            "basis": "新的契约依据",
        },
    )
    assert data["id"] == target["id"]
    assert data["versionNumber"] == target["versionNumber"]
    assert data["reviewStatus"] == target["reviewStatus"]
    assert data["name"] == "新名称"
    assert data["description"] == "新描述"
    assert data["scenario"] == "回归验证"
    assert data["basis"] == "新的契约依据"
    assert len(data["history"]) == 1


def test_edit_assertions_on_confirmed_creates_pending_review(client: TestClient, db_session: Session) -> None:
    """confirmed 版本改断言（可执行内容）：产生新版本且 review_status=pending_review。"""
    project_id = _project(client, "确认后改断言")
    items = _drafts(client, project_id, db_session)
    target = items[0]
    _confirm(client, target["id"])
    changed_assertions = list(target["assertions"]) + [
        {"type": "jsonType", "path": "extra", "expected": "string"}
    ]
    data = _edit(client, target["id"], {"assertions": changed_assertions})
    assert data["id"] != target["id"]
    assert data["versionNumber"] == target["versionNumber"] + 1
    assert data["reviewStatus"] == "pending_review"
    assert data["assertions"] == changed_assertions
    assert len(data["history"]) == 2


def test_edit_body_on_draft_creates_new_draft_version(client: TestClient, db_session: Session) -> None:
    """draft 版本改 body（可执行内容）：产生新版本且 review_status 仍为 draft。"""
    project_id = _project(client, "草稿改请求体")
    items = _drafts(client, project_id, db_session)
    target = _case(items, method="POST")
    new_body = {"name": "新商品", "price": 88.5}
    assert target["body"] != new_body
    data = _edit(client, target["id"], {"body": new_body})
    assert data["id"] != target["id"]
    assert data["versionNumber"] == target["versionNumber"] + 1
    assert data["reviewStatus"] == "draft"
    assert data["body"] == new_body
    assert len(data["history"]) == 2


def test_edit_same_executable_values_creates_no_new_version(client: TestClient, db_session: Session) -> None:
    """可执行内容传入与当前值相同的内容（断言、超时、键顺序不同的 body）：不产生新版本。"""
    project_id = _project(client, "相同可执行内容")
    items = _drafts(client, project_id, db_session)
    target = _case(items, method="POST")
    same_assertions = list(target["assertions"])
    data = _edit(
        client,
        target["id"],
        {"assertions": same_assertions, "timeout": target["timeout"]},
    )
    assert data["id"] == target["id"]
    assert data["versionNumber"] == target["versionNumber"]
    assert data["reviewStatus"] == target["reviewStatus"]
    assert len(data["history"]) == 1
    # JSON 键顺序不同但内容相同，规范化比较后仍应判为未变化。
    reversed_body = dict(reversed(list(target["body"].items())))
    data2 = _edit(client, target["id"], {"body": reversed_body})
    assert data2["id"] == target["id"]
    assert data2["versionNumber"] == target["versionNumber"]
    assert len(data2["history"]) == 1
