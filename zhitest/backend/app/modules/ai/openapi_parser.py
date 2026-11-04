"""OpenAPI 3.x 解析。不支持的 $ref 会记入错误，不静默丢弃。"""

from __future__ import annotations

import json
from typing import Any

import yaml

_METHODS = ("get", "post", "put", "patch", "delete")


def parse_openapi_document(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        raise ValueError("文档为空")
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        try:
            document = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"既不是 JSON 也不是 YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("OpenAPI 文档必须是对象")
    version = str(document.get("openapi") or "")
    if not version.startswith("3."):
        raise ValueError("只支持 OpenAPI 3.x，当前缺少 openapi: 3.x 声明")
    paths = document.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise ValueError("文档没有 paths")
    endpoints: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path, item in paths.items():
        if not isinstance(item, dict):
            errors.append({"loc": f"paths.{path}", "msg": "路径定义不是对象"})
            continue
        for method in _METHODS:
            operation = item.get(method)
            if operation is None:
                continue
            if not isinstance(operation, dict):
                errors.append({"loc": f"paths.{path}.{method}", "msg": "操作定义不是对象"})
                continue
            try:
                endpoints.append(_operation(document, str(path), method.upper(), operation))
            except ValueError as exc:
                errors.append({"loc": f"paths.{path}.{method}", "msg": str(exc)})
    if len(endpoints) > 300:
        raise ValueError("单次最多导入 300 个接口")
    if not endpoints:
        raise ValueError("没有解析出可导入的接口")
    return {"openapi": version, "endpoints": endpoints, "errors": errors}


def _operation(document: dict[str, Any], path: str, method: str, operation: dict[str, Any]) -> dict[str, Any]:
    parameters = operation.get("parameters") or []
    query: list[dict[str, Any]] = []
    path_params: list[dict[str, Any]] = []
    for parameter in parameters:
        if isinstance(parameter, dict) and "$ref" in parameter:
            parameter = _resolve(document, str(parameter["$ref"]), f"{method} {path} parameter")
        if not isinstance(parameter, dict):
            raise ValueError("参数不是对象")
        location = parameter.get("in")
        schema = _schema(document, parameter.get("schema") or {"type": "string"}, f"{method} {path}")
        field = {
            "name": parameter.get("name"),
            "type": schema.get("type") or "string",
            "required": bool(parameter.get("required")),
        }
        if location == "query":
            query.append(field)
        elif location == "path":
            field["required"] = True
            field["example"] = schema.get("example") or "sample"
            path_params.append(field)
    body = None
    request_body = operation.get("requestBody")
    if isinstance(request_body, dict):
        content = request_body.get("content") or {}
        json_body = content.get("application/json") if isinstance(content, dict) else None
        if isinstance(json_body, dict):
            body = _schema(document, json_body.get("schema") or {}, f"{method} {path} requestBody")
    responses: dict[str, Any] = {}
    raw_responses = operation.get("responses") or {}
    if isinstance(raw_responses, dict):
        for status, payload in raw_responses.items():
            if isinstance(payload, dict) and "$ref" in payload:
                payload = _resolve(document, str(payload["$ref"]), f"{method} {path} response")
            schema = {}
            if isinstance(payload, dict):
                content = payload.get("content") or {}
                json_body = content.get("application/json") if isinstance(content, dict) else None
                if isinstance(json_body, dict) and json_body.get("schema") is not None:
                    schema = _schema(document, json_body.get("schema"), f"{method} {path} {status}")
            responses[str(status)] = schema or {"description": "已声明"}
    return {
        "method": method,
        "path": path,
        "summary": str(operation.get("summary") or operation.get("operationId") or path),
        "requiresAuth": False,
        "query": query,
        "pathParams": path_params,
        "body": body,
        "responses": responses,
    }


def _schema(document: dict[str, Any], schema: Any, loc: str) -> dict[str, Any]:
    if not isinstance(schema, dict):
        raise ValueError(f"{loc} 的 schema 不是对象")
    if "$ref" in schema:
        schema = _resolve(document, str(schema["$ref"]), loc)
    properties = {}
    raw_properties = schema.get("properties") or {}
    if isinstance(raw_properties, dict):
        for name, value in raw_properties.items():
            properties[name] = _schema(document, value, f"{loc}.{name}")
    result: dict[str, Any] = {"type": schema.get("type") or ("object" if properties else "string")}
    if properties:
        result["properties"] = properties
    if schema.get("required"):
        result["required"] = list(schema["required"])
    for key in ("minimum", "maximum", "minLength", "maxLength", "example"):
        if key in schema:
            result[key] = schema[key]
    return result


def _resolve(document: dict[str, Any], ref: str, loc: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"{loc} 使用了无法解析的引用 {ref}")
    current: Any = document
    for part in ref[2:].split("/"):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"{loc} 引用不存在: {ref}")
        current = current[part]
    if not isinstance(current, dict):
        raise ValueError(f"{loc} 引用 {ref} 不是对象")
    if "$ref" in current:
        return _resolve(document, str(current["$ref"]), loc)
    return current
