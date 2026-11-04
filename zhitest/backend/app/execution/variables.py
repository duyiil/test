"""单次执行内的变量替换、提取和依赖排序。变量不写回其他运行。"""

from __future__ import annotations

import re
from typing import Any

from app.core.errors import AppError
from app.execution.assertions import lookup, parse_json

_TOKEN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def substitute(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        missing: list[str] = []

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in variables:
                missing.append(name)
                return match.group(0)
            return str(variables[name])

        rendered = _TOKEN.sub(replace, value)
        if missing:
            raise AppError(422, "VARIABLE_MISSING", f"使用了尚未产生的变量: {', '.join(missing)}")
        return rendered
    if isinstance(value, dict):
        return {key: substitute(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, variables) for item in value]
    return value


def produced_names(version: Any) -> list[str]:
    names = []
    for rule in version.extract or []:
        if isinstance(rule, dict) and rule.get("name"):
            names.append(str(rule["name"]))
    return names


def referenced_names(version: Any) -> set[str]:
    blob = str(
        {
            "path": version.relative_path,
            "headers": version.headers,
            "query": version.query,
            "path_params": version.path_params,
            "body": version.body,
        }
    )
    return set(_TOKEN.findall(blob))


def order_versions(versions: list[Any]) -> list[Any]:
    by_case = {str(item.case_id): item for item in versions}
    missing = []
    for version in versions:
        for dep in version.dependencies or []:
            if str(dep) not in by_case:
                missing.append(str(dep))
    if missing:
        raise AppError(422, "DEPENDENCY_INVALID", "存在缺少的前置用例，不能提交执行")
    indegree = {str(item.case_id): 0 for item in versions}
    children: dict[str, list[str]] = {key: [] for key in indegree}
    for version in versions:
        for dep in version.dependencies or []:
            children[str(dep)].append(str(version.case_id))
            indegree[str(version.case_id)] += 1
    ready = [key for key, degree in indegree.items() if degree == 0]
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if len(ordered) != len(versions):
        raise AppError(422, "DEPENDENCY_INVALID", "用例依赖存在循环")
    seen: set[str] = set()
    for case_id in ordered:
        for name in produced_names(by_case[case_id]):
            if name in seen:
                raise AppError(422, "VARIABLE_CONFLICT", f"变量 {name} 被重复定义")
            seen.add(name)
    available: set[str] = set()
    for case_id in ordered:
        needed = referenced_names(by_case[case_id])
        if not needed.issubset(available):
            raise AppError(422, "VARIABLE_MISSING", "使用了前置步骤不会产生的变量")
        available.update(produced_names(by_case[case_id]))
    return [by_case[case_id] for case_id in ordered]


def extract_values(rules: list[dict[str, Any]] | None, body_text: str) -> dict[str, Any]:
    if not rules:
        return {}
    ok, document = parse_json(body_text)
    if not ok:
        return {}
    found: dict[str, Any] = {}
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        name = str(rule.get("name") or "")
        path = str(rule.get("path") or "")
        if not name:
            continue
        state, value = lookup(document, path)
        if state == "found":
            found[name] = value
    return found
