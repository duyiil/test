"""四种断言：statusCode、jsonType、equals、range。"""

from __future__ import annotations

import json
from typing import Any


def parse_json(text: str) -> tuple[bool, Any]:
    try:
        return True, json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False, None


def json_kind(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unknown"


def lookup(document: Any, path: str) -> tuple[str, Any]:
    parts = [part for part in path.replace("$.", "").split(".") if part != ""]
    current = document
    for part in parts:
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index < 0 or index >= len(current):
                return "missing_field", None
            current = current[index]
            continue
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return "missing_field", None
    return "found", current


def evaluate_assertions(
    assertions: list[dict[str, Any]],
    *,
    status_code: int | None,
    body_text: str,
) -> list[dict[str, Any]]:
    is_json, document = parse_json(body_text) if body_text else (False, None)
    results: list[dict[str, Any]] = []
    for assertion in assertions:
        kind = assertion.get("type")
        if kind == "statusCode":
            expected = assertion.get("expected")
            passed = status_code == expected
            results.append(
                {
                    "type": "statusCode",
                    "passed": passed,
                    "errorClass": None if passed else "status_mismatch",
                    "expected": expected,
                    "actual": status_code,
                    "message": "状态码一致" if passed else f"期望 {expected}，实际 {status_code}",
                }
            )
            continue
        if not is_json:
            results.append(
                {
                    "type": kind,
                    "passed": False,
                    "errorClass": "non_json",
                    "expected": assertion.get("expected"),
                    "actual": None,
                    "message": "响应不是 JSON，无法做字段断言",
                }
            )
            continue
        path = str(assertion.get("path") or "")
        state, actual = lookup(document, path)
        if kind == "jsonType":
            results.append(_json_type(path, assertion.get("expected"), state, actual))
        elif kind == "equals":
            results.append(_equals(path, assertion.get("expected"), state, actual))
        elif kind == "range":
            results.append(_range(path, assertion.get("minimum"), assertion.get("maximum"), state, actual))
        else:
            results.append(
                {
                    "type": kind,
                    "passed": False,
                    "errorClass": "unknown_assertion",
                    "expected": None,
                    "actual": None,
                    "message": "不支持的断言类型",
                }
            )
    return results


def _json_type(path: str, expected: Any, state: str, actual: Any) -> dict[str, Any]:
    if state == "missing_field":
        return _fail("jsonType", "missing_field", expected, None, f"字段 {path or '<root>'} 不存在")
    actual_kind = json_kind(actual)
    if actual_kind == "null" and expected != "null":
        return _fail("jsonType", "null_value", expected, None, f"字段 {path} 为 null")
    if not _json_type_matches(expected, actual_kind):
        return _fail("jsonType", "type_mismatch", expected, actual_kind, f"字段 {path} 类型为 {actual_kind}")
    return _ok("jsonType", expected, actual_kind, f"字段 {path or '<root>'} 类型为 {actual_kind}")


def _json_type_matches(expected: Any, actual_kind: str) -> bool:
    if actual_kind == expected:
        return True
    # JSON Schema：integer 是 number 的子集。期望 integer 时仍拒绝小数。
    return expected == "number" and actual_kind == "integer"


def _equals(path: str, expected: Any, state: str, actual: Any) -> dict[str, Any]:
    if state == "missing_field":
        return _fail("equals", "missing_field", expected, None, f"字段 {path or '<root>'} 不存在")
    if json_kind(actual) == json_kind(expected) and actual == expected:
        return _ok("equals", expected, actual, "严格相等")
    return _fail("equals", "strict_mismatch", expected, actual, "实际值与期望值严格不相等")


def _range(path: str, minimum: Any, maximum: Any, state: str, actual: Any) -> dict[str, Any]:
    if state == "missing_field":
        return _fail("range", "missing_field", {"minimum": minimum, "maximum": maximum}, None, f"字段 {path} 不存在")
    if actual is None:
        return _fail("range", "null_value", {"minimum": minimum, "maximum": maximum}, None, f"字段 {path} 为 null")
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return _fail(
            "range",
            "type_mismatch",
            {"minimum": minimum, "maximum": maximum},
            actual,
            "区间断言不接受字符串数字或非数值",
        )
    if (minimum is not None and actual < minimum) or (maximum is not None and actual > maximum):
        return _fail("range", "out_of_range", {"minimum": minimum, "maximum": maximum}, actual, "数值不在区间内")
    return _ok("range", {"minimum": minimum, "maximum": maximum}, actual, "数值在区间内")


def _ok(kind: str, expected: Any, actual: Any, message: str) -> dict[str, Any]:
    return {"type": kind, "passed": True, "errorClass": None, "expected": expected, "actual": actual, "message": message}


def _fail(kind: str, error_class: str, expected: Any, actual: Any, message: str) -> dict[str, Any]:
    return {
        "type": kind,
        "passed": False,
        "errorClass": error_class,
        "expected": expected,
        "actual": actual,
        "message": message,
    }
