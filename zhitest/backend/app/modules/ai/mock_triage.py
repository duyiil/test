"""Mock 研判：按 7 类内置 bug 规则对失败结果做归因。

柴诗雨任务：TriageProvider mock 研判。没有配置真实模型密钥时，
用内置规则对断言失败做模式匹配，输出分组根因与定位建议，
替代原来的 unavailable 占位。

规则只做模式匹配，不是模型分析。结论必须标注来源，
避免把 Mock 结果说成 AI 结论。
"""

from __future__ import annotations

from typing import Any

from app.modules.ai.llm_provider import failure_details

MOCK_TRIAGE_LABEL = "规则研判（Mock，未调用真实模型）"

# 7 类内置 bug 规则，与 demo/sut/README.md 列出的 7 个缺陷一一对应。
# 每条规则：key、名称、匹配函数（入参为失败明细行）、结论模板。
RULES: list[dict[str, Any]] = [
    {
        "key": "missing_404",
        "title": "商品不存在时未返回 404",
        "match": lambda row: (
            row.get("method") == "GET"
            and "/api/products/" in row.get("path", "")
            and any(
                item.get("type") == "statusCode" and item.get("expected") == 404 and item.get("actual") == 200
                for item in row.get("failedAssertions") or []
            )
        ),
        "advice": "接口对不存在的商品仍返回 200，未按契约声明返回 404。建议检查资源查询为空时的响应逻辑，改为返回 404 及错误体。",
    },
    {
        "key": "required_name_missing",
        "title": "缺少必填字段 name 未拒绝",
        "match": lambda row: (
            row.get("method") == "POST"
            and row.get("responseStatus") == 201
            and ("缺少" in (row.get("name") or "") or "必填" in (row.get("name") or ""))
            and any(
                item.get("type") == "statusCode" and item.get("expected") == 400 and item.get("actual") == 201
                for item in row.get("failedAssertions") or []
            )
        ),
        "advice": "请求体缺少必填字段 name 时仍返回 201 并创建成功。建议在入口处增加必填校验，缺失时返回 400。",
    },
    {
        "key": "price_type_not_validated",
        "title": "price 类型错误未拒绝",
        "match": lambda row: (
            row.get("method") == "POST"
            and row.get("responseStatus") == 201
            and ("字符串" in (row.get("name") or "") or "类型" in (row.get("name") or ""))
            and any(
                item.get("type") == "statusCode" and item.get("expected") == 400 and item.get("actual") == 201
                for item in row.get("failedAssertions") or []
            )
        ),
        "advice": "price 传入字符串仍返回 201 并按原样保存。建议增加参数类型校验，类型不合法时返回 400。",
    },
    {
        "key": "price_boundary",
        "title": "price 边界值未校验",
        "match": lambda row: (
            row.get("method") == "POST"
            and row.get("responseStatus") == 201
            and (
                "为 0" in (row.get("name") or "")
                or "边界" in (row.get("name") or "")
                or '"price": 0' in str(row.get("responseSnippet") or "")
            )
            and any(
                item.get("type") == "statusCode" and item.get("expected") == 400 and item.get("actual") == 201
                for item in row.get("failedAssertions") or []
            )
        ),
        "advice": "price 传 0 仍被接受，未校验契约声明的最小值 0.01。建议增加数值边界校验（最小值/最大值）。",
    },
    {
        "key": "name_max_length",
        "title": "name 超长未拒绝",
        "match": lambda row: (
            row.get("method") == "POST"
            and row.get("responseStatus") == 201
            and "长度" in (row.get("name") or "")
            and any(
                item.get("type") == "statusCode" and item.get("expected") == 400 and item.get("actual") == 201
                for item in row.get("failedAssertions") or []
            )
        ),
        "advice": "name 超过契约声明的 40 字符上限仍返回 201。建议增加最大长度校验，超长时返回 400。",
    },
    {
        "key": "seed_data_type",
        "title": "种子数据字段类型与契约不符",
        "match": lambda row: (
            row.get("method") == "GET"
            and any(
                item.get("type") == "jsonType" and item.get("expected") == "number" and item.get("actual") == "string"
                for item in row.get("failedAssertions") or []
            )
        ),
        "advice": "响应中 price 实际为字符串，与契约声明的 number 不符。疑似预置数据脏数据。建议清理种子数据，并在写入侧增加类型校验。",
    },
    {
        "key": "duplicate_name",
        "title": "重名商品重复创建成功",
        "match": lambda row: (
            row.get("method") == "POST"
            and row.get("responseStatus") == 201
            and ("重复" in (row.get("name") or "") or "重名" in (row.get("name") or ""))
        ),
        "advice": "相同 name 的商品可以重复创建且每次都返回 201。若业务要求名称唯一，建议增加重名校验或数据库唯一约束。",
    },
]


_OTHER_RULE = {
    "title": "未匹配内置规则的失败",
    "advice": "失败模式不在 7 类内置规则内。建议人工核对请求与响应，或配置真实研判模型进一步分析。",
}


def _match_rule(row: dict[str, Any]) -> str:
    """返回命中的规则 key；未命中时返回 "other"。"""

    for rule in RULES:
        try:
            if rule["match"](row):
                return str(rule["key"])
        except Exception:
            continue
    return "other"


def _group_text(title: str, advice: str, cases: list[str]) -> str:
    unique = list(dict.fromkeys(cases))
    shown = "、".join(unique[:5])
    more = f" 等 {len(unique)} 条用例" if len(unique) > 5 else ""
    return f"    {title}（涉及：{shown}{more}）\n    建议：{advice}"


class MockTriageProvider:
    """规则研判。只依赖失败明细，不发网络请求。"""

    name = "mock-triage"

    def triage(self, report: dict[str, Any]) -> str:
        failures = failure_details(report)
        if not failures:
            return f"{MOCK_TRIAGE_LABEL}：本次执行没有失败用例，无需归因。"

        groups: dict[str, dict[str, Any]] = {}
        for row in failures:
            key = _match_rule(row)
            rule = next((item for item in RULES if item["key"] == key), _OTHER_RULE)
            group = groups.setdefault(key, {"title": rule["title"], "advice": rule["advice"], "cases": []})
            group["cases"].append(row.get("name") or row.get("path") or "未知用例")

        parts = [MOCK_TRIAGE_LABEL + "："]
        for index, group in enumerate(groups.values(), start=1):
            parts.append(f"{index}." + _group_text(group["title"], group["advice"], group["cases"]))
        parts.append("以上结论由内置规则匹配得出，未调用真实模型，仅供参考。")
        return "\n".join(parts)
