"""确定性 Mock 生成器。

只根据调用方传入的契约生成草稿。不导入演示服务，也不把未声明的状态码写成预期。
"""

from __future__ import annotations

from typing import Any


class MockGenerationProvider:
    name = "mock"

    def generate(self, *, project_name: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
        method = str(contract["method"]).upper()
        path = str(contract["path"])
        responses = {str(key): value for key, value in dict(contract.get("responses") or {}).items()}
        cases: list[dict[str, Any]] = []
        success = _success_status(method, responses)
        if success is not None:
            cases.append(_happy_case(project_name, method, path, contract, responses[success], int(success)))
        if "400" in responses:
            missing = _missing_required_case(method, path, contract)
            if missing is not None:
                cases.append(missing)
            boundary = _boundary_case(method, path, contract)
            if boundary is not None:
                cases.append(boundary)
            typed = _wrong_type_case(method, path, contract)
            if typed is not None:
                cases.append(typed)
        if contract.get("requiresAuth") is True and "401" in responses:
            cases.append(_unauthorized_case(method, path))
        elif contract.get("requiresAuth") is True and "401" not in responses:
            # 契约写了需要登录，但没有声明 401。不发明 401。
            pass
        not_found = _not_found_case(method, path, contract, responses)
        if not_found is not None:
            cases.append(not_found)
        return cases


def _success_status(method: str, responses: dict[str, Any]) -> str | None:
    if method == "POST" and "201" in responses:
        return "201"
    if "200" in responses:
        return "200"
    for code in ("201", "202", "204"):
        if code in responses:
            return code
    return None


def _happy_case(
    project_name: str,
    method: str,
    path: str,
    contract: dict[str, Any],
    response_schema: Any,
    status: int,
) -> dict[str, Any]:
    assertions: list[dict[str, Any]] = [{"type": "statusCode", "expected": status}]
    if isinstance(response_schema, dict):
        properties = response_schema.get("properties") or {}
        if isinstance(properties, dict):
            for name, schema in properties.items():
                if isinstance(schema, dict) and schema.get("type") in {
                    "integer",
                    "number",
                    "string",
                    "boolean",
                    "object",
                    "array",
                    "null",
                }:
                    assertions.append({"type": "jsonType", "path": str(name), "expected": schema["type"]})
    return {
        "name": f"{method} {path} 正常响应",
        "description": f"依据契约中声明的 {status} 响应。项目：{project_name}。",
        "scenario": "正常功能",
        "basis": f"契约声明 {method} {path} 可以返回 {status}，字段类型来自该响应结构。",
        "method": method,
        "relativePath": path,
        "headers": {},
        "query": _sample_query(contract, invalid=False),
        "pathParams": _sample_path(contract, missing=False),
        "body": _sample_body(contract, mode="valid"),
        "timeout": 30,
        "assertions": assertions,
        "origin": "mock",
    }


def _missing_required_case(method: str, path: str, contract: dict[str, Any]) -> dict[str, Any] | None:
    body = contract.get("body") if isinstance(contract.get("body"), dict) else None
    required = list(body.get("required") or []) if body else []
    if not required:
        return None
    omitted = str(required[0])
    return {
        "name": f"{method} {path} 缺少必填 {omitted}",
        "description": f"不提交契约标为必填的 {omitted}。",
        "scenario": "必填项",
        "basis": f"契约将 {omitted} 标为必填，并声明了 400。预期状态码只来自该声明。",
        "method": method,
        "relativePath": path,
        "headers": {},
        "query": {},
        "pathParams": _sample_path(contract, missing=False),
        "body": _sample_body(contract, mode="omit", omit=omitted),
        "timeout": 30,
        "assertions": [{"type": "statusCode", "expected": 400}],
        "origin": "mock",
    }


def _boundary_case(method: str, path: str, contract: dict[str, Any]) -> dict[str, Any] | None:
    body = contract.get("body") if isinstance(contract.get("body"), dict) else None
    properties = body.get("properties") if body else None
    if not isinstance(properties, dict):
        return None
    for name, schema in properties.items():
        if not isinstance(schema, dict):
            continue
        if schema.get("type") == "number" and isinstance(schema.get("minimum"), (int, float)):
            below = float(schema["minimum"]) - 0.01
            sample = _sample_body(contract, mode="valid")
            if not isinstance(sample, dict):
                return None
            sample[str(name)] = below
            return {
                "name": f"{method} {path} {name} 低于最小值",
                "description": f"{name} 取契约最小值减去 0.01。",
                "scenario": "边界值",
                "basis": f"契约声明 {name} 最小值为 {schema['minimum']}，并声明了 400。",
                "method": method,
                "relativePath": path,
                "headers": {},
                "query": {},
                "pathParams": _sample_path(contract, missing=False),
                "body": sample,
                "timeout": 30,
                "assertions": [{"type": "statusCode", "expected": 400}],
                "origin": "mock",
            }
        if schema.get("type") == "string" and isinstance(schema.get("maxLength"), int):
            sample = _sample_body(contract, mode="valid")
            if not isinstance(sample, dict):
                return None
            sample[str(name)] = "测" * (int(schema["maxLength"]) + 1)
            return {
                "name": f"{method} {path} {name} 超过最大长度",
                "description": f"{name} 长度比契约 maxLength 多 1。",
                "scenario": "边界值",
                "basis": f"契约声明 {name} 最大长度为 {schema['maxLength']}，并声明了 400。",
                "method": method,
                "relativePath": path,
                "headers": {},
                "query": {},
                "pathParams": _sample_path(contract, missing=False),
                "body": sample,
                "timeout": 30,
                "assertions": [{"type": "statusCode", "expected": 400}],
                "origin": "mock",
            }
    return None


def _wrong_type_case(method: str, path: str, contract: dict[str, Any]) -> dict[str, Any] | None:
    body = contract.get("body") if isinstance(contract.get("body"), dict) else None
    properties = body.get("properties") if body else None
    if not isinstance(properties, dict):
        return None
    for name, schema in properties.items():
        if isinstance(schema, dict) and schema.get("type") == "number":
            sample = _sample_body(contract, mode="valid")
            if not isinstance(sample, dict):
                return None
            sample[str(name)] = "10"
            return {
                "name": f"{method} {path} {name} 使用字符串",
                "description": f"契约要求 {name} 为 number，请求里改为字符串。",
                "scenario": "数据类型",
                "basis": "契约声明该字段类型为 number，并声明了 400。字符串和数字不自动转换。",
                "method": method,
                "relativePath": path,
                "headers": {},
                "query": {},
                "pathParams": _sample_path(contract, missing=False),
                "body": sample,
                "timeout": 30,
                "assertions": [{"type": "statusCode", "expected": 400}],
                "origin": "mock",
            }
    return None


def _unauthorized_case(method: str, path: str) -> dict[str, Any]:
    return {
        "name": f"{method} {path} 未登录",
        "description": "契约声明该接口需要登录，并且声明了 401。",
        "scenario": "身份认证",
        "basis": "只有契约同时声明 requiresAuth 和 401 时才生成这条预期。",
        "method": method,
        "relativePath": path,
        "headers": {},
        "query": {},
        "pathParams": {},
        "body": None,
        "timeout": 30,
        "assertions": [{"type": "statusCode", "expected": 401}],
        "origin": "mock",
    }


def _not_found_case(
    method: str,
    path: str,
    contract: dict[str, Any],
    responses: dict[str, Any],
) -> dict[str, Any] | None:
    if "404" not in responses or "{" not in path:
        return None
    return {
        "name": f"{method} {path} 资源不存在",
        "description": "使用契约示例之外的路径参数。",
        "scenario": "契约状态码",
        "basis": "契约声明了 404。不根据接口名称推测其他状态码。",
        "method": method,
        "relativePath": path,
        "headers": {},
        "query": {},
        "pathParams": _sample_path(contract, missing=True),
        "body": None,
        "timeout": 30,
        "assertions": [{"type": "statusCode", "expected": 404}],
        "origin": "mock",
    }


def _sample_query(contract: dict[str, Any], *, invalid: bool) -> dict[str, Any]:
    query = contract.get("query") if isinstance(contract.get("query"), list) else []
    values: dict[str, Any] = {}
    for item in query:
        if not isinstance(item, dict) or item.get("required") is not True:
            continue
        values[str(item["name"])] = 0 if invalid else 1
    return values


def _sample_path(contract: dict[str, Any], *, missing: bool) -> dict[str, Any]:
    params = contract.get("pathParams") if isinstance(contract.get("pathParams"), list) else []
    values: dict[str, Any] = {}
    for item in params:
        if not isinstance(item, dict):
            continue
        name = str(item["name"])
        values[name] = "missing-item" if missing else item.get("example") or "sample"
    return values


def _sample_body(contract: dict[str, Any], *, mode: str, omit: str | None = None) -> dict[str, Any] | None:
    body = contract.get("body")
    if not isinstance(body, dict):
        return None
    properties = body.get("properties") if isinstance(body.get("properties"), dict) else {}
    sample: dict[str, Any] = {}
    for name, schema in properties.items():
        if mode == "omit" and name == omit:
            continue
        if not isinstance(schema, dict):
            continue
        if "example" in schema:
            sample[str(name)] = schema["example"]
        elif schema.get("type") == "string":
            sample[str(name)] = "示例"
        elif schema.get("type") == "integer":
            sample[str(name)] = 1
        elif schema.get("type") == "number":
            sample[str(name)] = 1
        elif schema.get("type") == "boolean":
            sample[str(name)] = True
    return sample
