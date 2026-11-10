"""柴诗雨功能：TriageProvider mock 研判（7 类内置 bug 规则）。

对应测试用例 TCM-TRIAGE-001 ~ 010，见本目录 README。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.ai.mock_triage import MOCK_TRIAGE_LABEL, RULES, MockTriageProvider

pytestmark = pytest.mark.anyio

# 7 条规则的期望输出片段（按 key 排序）
EXPECTED_TITLES = {
    "missing_404": "商品不存在时未返回 404",
    "required_name_missing": "缺少必填字段 name 未拒绝",
    "price_type_not_validated": "price 类型错误未拒绝",
    "price_boundary": "price 边界值未校验",
    "name_max_length": "name 超长未拒绝",
    "seed_data_type": "种子数据字段类型与契约不符",
    "duplicate_name": "重名商品重复创建成功",
}


def _failure_row(name: str, method: str, path: str, status: int, assertions: list[dict[str, Any]], body: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "method": method,
        "path": path,
        "responseStatus": status,
        "errorClass": "assertion_failed",
        "errorMessage": "存在未通过的断言",
        "failedAssertions": assertions,
        "responseBody": body,
    }


def _report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "passedCount": 0,
        "assertionFailedCount": len(rows),
        "executionErrorCount": 0,
        "passRateText": "0%",
        "results": [
            {"name": r["name"], "method": r["method"], "path": r["path"], "status": "assertion_failed",
             "responseStatus": r["responseStatus"], "errorClass": r["errorClass"], "errorMessage": r["errorMessage"],
             "assertionResults": r["failedAssertions"], "request": {}, "responseBody": r["responseBody"]}
            for r in rows
        ],
    }


STATUS_400_EXPECTED = {"type": "statusCode", "expected": 400, "actual": 201, "passed": False}


def _rows_for_all_rules() -> list[dict[str, Any]]:
    return [
        _failure_row("GET /api/products/{id} 资源不存在", "GET", "/api/products/unknown", 200,
                     [{"type": "statusCode", "expected": 404, "actual": 200, "passed": False}]),
        _failure_row("POST /api/products 缺少必填 name", "POST", "/api/products", 201, [STATUS_400_EXPECTED]),
        _failure_row("POST /api/products price 使用字符串", "POST", "/api/products", 201, [STATUS_400_EXPECTED]),
        _failure_row("POST /api/products price 为 0", "POST", "/api/products", 201, [STATUS_400_EXPECTED],
                     body='{"price": 0}'),
        _failure_row("POST /api/products name 超过最大长度", "POST", "/api/products", 201, [STATUS_400_EXPECTED]),
        _failure_row("GET /api/products/{id} 正常响应", "GET", "/api/products/p-1", 200,
                     [{"type": "jsonType", "expected": "number", "actual": "string", "passed": False}]),
        _failure_row("POST /api/products 重复 name 创建", "POST", "/api/products", 201, [STATUS_400_EXPECTED]),
    ]


def test_rules_cover_seven_builtin_bugs() -> None:
    """TCM-TRIAGE-001：规则表恰好覆盖 demo/sut 的 7 类内置 bug。"""

    assert len(RULES) == 7
    assert {rule["key"] for rule in RULES} == set(EXPECTED_TITLES)


@pytest.mark.parametrize(
    ("key", "row"),
    list(zip(EXPECTED_TITLES, _rows_for_all_rules())),
    ids=list(EXPECTED_TITLES),
)
def test_each_rule_matches_its_own_failure(key: str, row: dict[str, Any]) -> None:
    """TCM-TRIAGE-002~008：7 类失败各自命中对应规则并输出标题与建议。"""

    text = MockTriageProvider().triage(_report([row]))
    assert MOCK_TRIAGE_LABEL in text
    assert EXPECTED_TITLES[key] in text
    assert "建议：" in text


def test_grouped_output_when_all_seven_fail() -> None:
    """TCM-TRIAGE-009：7 类失败同时出现时按规则分组输出，且标注非模型分析。"""

    text = MockTriageProvider().triage(_report(_rows_for_all_rules()))
    assert MOCK_TRIAGE_LABEL in text
    for title in EXPECTED_TITLES.values():
        assert title in text
    assert "未调用真实模型" in text


def test_no_failure_returns_placeholder() -> None:
    """TCM-TRIAGE-010：没有失败用例时返回无归因说明，不抛异常。"""

    text = MockTriageProvider().triage(_report([]))
    assert MOCK_TRIAGE_LABEL in text
    assert "无需归因" in text
