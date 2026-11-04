"""真实模型常见输出形状。只用假传输，不访问 api.deepseek.com。"""

from __future__ import annotations

import json
import logging
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.ai.llm_provider import (
    LLMGenerationProvider,
    TRIAGE_CHAR_LIMIT,
    apply_triage,
    bound_model_text,
    failure_details,
    normalize_generated_case,
)
from app.modules.testing.service import partition_generated_cases, process_generation_task, validate_generated_case
from tests.helpers import login


def _nested_case() -> dict:
    return {
        "name": "查询商品",
        "request": {"method": "GET", "path": "https://sut.example/api/products?page=1"},
        "assertions": [
            {"type": "status", "expected": 200},
            {"type": "bodyPath", "path": "$.items", "expected": "array"},
            {"type": "bodyPath", "path": "price", "expected": 12.5},
            {"type": "equal", "path": "name", "expect": "水杯"},
        ],
    }


def test_generate_normalizes_real_world_shape_and_uses_json_mode() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode())
        payload = {
            "cases": [
                _nested_case(),
                {
                    "name": "坏方法",
                    "request": {"method": "TRACE", "path": "/api/products"},
                    "assertions": [{"type": "status", "expected": 200}],
                },
            ]
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]})

    provider = LLMGenerationProvider(
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        api_key="sk-test-secret",
        transport=httpx.MockTransport(handler),
    )
    cases = provider.generate(project_name="商品", contract={"method": "GET", "path": "/api/products"})
    body = seen["body"]
    assert body["response_format"] == {"type": "json_object"}
    system = body["messages"][0]["content"]
    user = body["messages"][1]["content"]
    assert "json" in system
    assert "relativePath" in system
    assert "statusCode" in user
    assert "schemaExample" in user
    assert "sk-test-secret" not in user

    good = cases[0]
    assert good["method"] == "GET"
    assert good["relativePath"] == "/api/products"
    assert good["origin"] == "llm"
    assert good["assertions"][0] == {"type": "statusCode", "expected": 200}
    assert good["assertions"][1] == {"type": "jsonType", "path": "items", "expected": "array"}
    assert good["assertions"][2] == {"type": "equals", "path": "price", "expected": 12.5}
    assert good["assertions"][3] == {"type": "equals", "path": "name", "expected": "水杯"}
    assert cases[1]["method"] == "TRACE"

    accepted, errors = partition_generated_cases(cases, {"method": "GET", "path": "/api/products"})
    assert len(accepted) == 1
    assert accepted[0]["name"] == "查询商品"
    assert len(errors) == 1
    assert "用例「坏方法」" in errors[0]
    assert "无效请求方法 'TRACE'" in errors[0]


def test_path_mismatch_names_the_case() -> None:
    case = normalize_generated_case(
        {
            "name": "错路径",
            "request": {"method": "GET", "path": "/nope"},
            "assertions": [{"type": "status", "expected": 200}],
        }
    )
    with pytest.raises(ValueError) as caught:
        validate_generated_case(case, {"path": "/api/products"})
    message = str(caught.value)
    assert "用例「错路径」" in message
    assert "/nope" in message
    assert "/api/products" in message


def test_mock_shape_stays_valid() -> None:
    original = {
        "name": "GET /api/products 正常响应",
        "description": "ok",
        "scenario": "正常功能",
        "basis": "契约",
        "method": "GET",
        "relativePath": "/api/products",
        "headers": {},
        "query": {},
        "pathParams": {},
        "body": None,
        "timeout": 30,
        "assertions": [
            {"type": "statusCode", "expected": 200},
            {"type": "jsonType", "path": "items", "expected": "array"},
        ],
        "origin": "mock",
    }
    normalized = normalize_generated_case(original)
    validate_generated_case(normalized, {"path": "/api/products"})
    assert normalized["origin"] == "mock"
    assert normalized["method"] == "GET"
    assert normalized["assertions"] == original["assertions"]


def test_triage_sends_failure_details_not_only_counts() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"choices": [{"message": {"content": "价格字段被写成了字符串。建议核对商品种子数据。"}}]})

    report = {
        "status": "succeeded",
        "passedCount": 8,
        "assertionFailedCount": 10,
        "passRateText": "44%",
        "results": [
            {"status": "passed", "name": "列表成功", "assertionResults": []},
            {
                "status": "assertion_failed",
                "name": "价格类型",
                "method": "GET",
                "path": "/api/products/p-1",
                "request": {"method": "GET", "url": "http://127.0.0.1:9000/api/products/p-1"},
                "responseStatus": 200,
                "errorClass": "assertion_failed",
                "errorMessage": "存在未通过的断言",
                "responseBody": '{"price":"12.5","token":"sk-should-not-pass"}',
                "assertionResults": [
                    {
                        "type": "jsonType",
                        "passed": False,
                        "expected": "number",
                        "actual": "string",
                        "message": "字段 price 类型为 string",
                    }
                ],
            },
        ],
    }
    provider = LLMGenerationProvider(
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        api_key="sk-test-secret",
        transport=httpx.MockTransport(handler),
    )
    text = provider.triage(report)
    assert "价格" in text
    body = seen["body"]
    assert "response_format" not in body
    assert "根因" in body["messages"][0]["content"]
    user = body["messages"][1]["content"]
    assert "价格类型" in user
    assert "number" in user
    assert "string" in user
    assert "/api/products/p-1" in user
    assert "sk-should-not-pass" not in user
    assert "sk-***" in user
    details = failure_details(report)
    assert details[0]["failedAssertions"][0]["expected"] == "number"
    assert details[0]["failedAssertions"][0]["actual"] == "string"


def test_triage_text_stops_at_a_sentence_when_truncated() -> None:
    short = "价格字段是字符串。"
    assert bound_model_text(short) == short
    long = "第一组：价格被写成字符串。建议核对种子数据。" + ("后续句子很长。" * 2000)
    limited = bound_model_text(long, limit=40)
    assert limited.endswith("（已截断）")
    assert len(limited) <= 40
    assert limited.startswith("第一组：价格被写成字符串。")
    assert limited.removesuffix("（已截断）").endswith("。")
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"choices": [{"message": {"content": long}}]})

    provider = LLMGenerationProvider(
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        api_key="sk-test-secret",
        transport=httpx.MockTransport(handler),
    )
    text = provider.triage({"results": [], "passedCount": 0, "assertionFailedCount": 1, "passRateText": "0%"})
    assert seen["body"]["max_tokens"] == 2048
    assert "response_format" not in seen["body"]
    assert text.endswith("（已截断）")
    assert len(text) <= TRIAGE_CHAR_LIMIT
    assert "第一组：价格被写成字符串。" in text


def test_triage_failure_is_logged_without_the_key(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    caplog.set_level(logging.WARNING, logger="zhitest.llm")

    def explode(self: LLMGenerationProvider, report: dict) -> str:
        raise RuntimeError("调用失败 sk-test-secret Bearer sk-test-secret")

    monkeypatch.setattr(LLMGenerationProvider, "triage", explode)
    status, message = apply_triage(
        {"results": []},
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        api_key="sk-test-secret",
    )
    assert status == "failed"
    assert message.startswith("研判失败，数据报告仍可查看。原因：")
    assert "sk-test-secret" not in message
    assert "sk-test-secret" not in caplog.text
    assert "llm triage failed" in caplog.text


class _NestedProvider:
    name = "llm"
    model = "deepseek-chat"

    def generate(self, *, project_name: str, contract: dict) -> list[dict]:
        path = contract["path"]
        method = contract["method"]
        return [
            {
                "name": f"{method} {path} 可用",
                "request": {"method": method, "path": path},
                "assertions": [
                    {"type": "status", "expected": 200},
                    {"type": "bodyPath", "path": "items", "expected": "array"},
                ],
            },
            {
                "name": "坏方法",
                "request": {"method": "TRACE", "path": path},
                "assertions": [{"type": "status", "expected": 200}],
            },
        ]


class _InvalidProvider:
    name = "llm"
    model = "deepseek-chat"

    def generate(self, *, project_name: str, contract: dict) -> list[dict]:
        return [
            {
                "name": "坏方法",
                "request": {"method": "TRACE", "path": contract["path"]},
                "assertions": [{"type": "status", "expected": 200}],
            }
        ]


def _project(client: TestClient) -> str:
    login(client)
    response = client.post(
        "/api/v1/projects",
        json={"name": "归一化", "description": "", "baseUrl": "http://127.0.0.1:9000", "envLabel": "测试"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def test_worker_keeps_valid_cases_and_records_provider(client: TestClient, db_session: Session) -> None:
    project_id = _project(client)
    loaded = client.post(f"/api/v1/projects/{project_id}/contract/demo")
    assert loaded.status_code == 200, loaded.text
    created = client.post(f"/api/v1/projects/{project_id}/generation-tasks")
    assert created.status_code == 202, created.text
    assert created.json()["data"]["provider"] == "mock"
    task_id = uuid.UUID(created.json()["data"]["id"])
    process_generation_task(db_session, task_id, provider=_NestedProvider())
    detail = client.get(f"/api/v1/generation-tasks/{task_id}")
    body = detail.json()["data"]
    assert body["provider"] == "llm"
    assert body["model"] == "deepseek-chat"
    assert body["status"] == "succeeded"
    assert body["targets"]
    assert all(item["status"] == "succeeded" for item in body["targets"])
    assert all(item["error"] and "部分用例未采用" in item["error"] and "无效请求方法" in item["error"] for item in body["targets"])
    cases = client.get(f"/api/v1/projects/{project_id}/cases").json()["data"]["items"]
    assert len(cases) == 3
    assert {item["origin"] for item in cases} == {"llm"}
    assert all(item["method"] != "TRACE" for item in cases)
    assert all(item["assertions"][0]["type"] == "statusCode" for item in cases)


def test_all_invalid_cases_fail_the_target_with_case_errors(client: TestClient, db_session: Session) -> None:
    project_id = _project(client)
    client.post(f"/api/v1/projects/{project_id}/contract/demo")
    created = client.post(f"/api/v1/projects/{project_id}/generation-tasks")
    task_id = uuid.UUID(created.json()["data"]["id"])
    process_generation_task(db_session, task_id, provider=_InvalidProvider())
    detail = client.get(f"/api/v1/generation-tasks/{task_id}").json()["data"]
    assert detail["status"] == "failed"
    assert detail["provider"] == "llm"
    assert detail["model"] == "deepseek-chat"
    assert detail["succeededCount"] == 0
    assert all(item["status"] == "failed" for item in detail["targets"])
    assert all(item["attempts"] == 2 for item in detail["targets"])
    assert all("用例「坏方法」" in (item["error"] or "") and "无效请求方法 'TRACE'" in (item["error"] or "") for item in detail["targets"])
    cases = client.get(f"/api/v1/projects/{project_id}/cases").json()["data"]["items"]
    assert cases == []
