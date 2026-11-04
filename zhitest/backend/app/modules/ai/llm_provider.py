"""OpenAI 兼容的生成与研判。

默认指向 DeepSeek。密钥只从环境变量读取，不写入日志。
没有密钥时调用方应继续使用 Mock，而不是在这里编造结果。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger("zhitest.llm")

JSON_KINDS = {"integer", "number", "string", "boolean", "object", "array", "null"}
_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_\-]{4,}")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+\S+")

GENERATE_SYSTEM = (
    "你是接口测试用例生成器。只输出 json，不要输出解释。"
    "顶层必须是 json 对象，格式为 {\"cases\": [用例, ...]}。"
    "每条用例把 method 和 relativePath 放在顶层，不要包在 request 里。"
    "assertions[].type 只能是 statusCode、jsonType、equals、range。"
    "statusCode 的 expected 是整数状态码；jsonType 的 expected 是 integer、number、string、boolean、object、array 或 null。"
    "只根据给定契约生成，契约没有声明的状态码不要写进断言。"
)

TRIAGE_CHAR_LIMIT = 12000
TRIAGE_MAX_TOKENS = 2048
_TRUNCATION_MARK = "（已截断）"

TRIAGE_SYSTEM = (
    "你是测试结果研判助手。请用中文给出分组根因分析和修复建议。"
    "只根据失败明细里的用例名、方法、路径、期望值、实际值和响应片段下结论。"
    "相同原因合并成一组，并给出可核对的建议。"
    "每组先写原因再写建议，每组不超过四句，写完一组再写下组，不要把句子写到一半。"
    "不要只用通过数、失败数和通过率复述结果，也不要粘贴完整响应。"
    "证据不足时写待核对，不要把未验证的问题说成已确认漏洞。"
)

SCHEMA_EXAMPLE = {
    "cases": [
        {
            "name": "查询商品列表成功",
            "description": "契约声明该接口可以返回 200。",
            "scenario": "正常功能",
            "basis": "契约声明 GET /api/products 返回 200，items 为 array。",
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
        }
    ]
}


class LLMGenerationProvider:
    name = "llm"

    def __init__(self, *, base_url: str, model: str, api_key: str, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        self._transport = transport

    def generate(self, *, project_name: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
        prompt = {
            "project": project_name,
            "contract": contract,
            "output": "json",
            "schemaExample": SCHEMA_EXAMPLE,
            "rules": [
                "只根据给定契约生成用例",
                "契约没有声明的状态码不要写入断言",
                "每条用例必须有 assertions",
                "method 与 relativePath 放在用例顶层",
                "输出 json 对象，键为 cases，值是用例数组",
            ],
        }
        content = self._chat(GENERATE_SYSTEM, json.dumps(prompt, ensure_ascii=False), json_mode=True)
        parsed = _load_json(content)
        cases = _unwrap_cases(parsed)
        normalized: list[Any] = []
        for item in cases:
            if isinstance(item, dict):
                case = normalize_generated_case(item)
                case["origin"] = "llm"
                normalized.append(case)
            else:
                normalized.append(item)
        return normalized

    def triage(self, report: dict[str, Any]) -> str:
        failures = failure_details(report)
        content = self._chat(
            TRIAGE_SYSTEM,
            json.dumps(
                {
                    "status": report.get("status"),
                    "passed": report.get("passedCount"),
                    "assertionFailed": report.get("assertionFailedCount"),
                    "executionError": report.get("executionErrorCount"),
                    "passRateText": report.get("passRateText"),
                    "failures": failures,
                    "instruction": "按根因分组，说明期望与实际差异，并给出建议。不要只复述数量。",
                },
                ensure_ascii=False,
            ),
            json_mode=False,
            max_tokens=TRIAGE_MAX_TOKENS,
        )
        return bound_model_text(content)

    def _chat(self, system: str, user: str, *, json_mode: bool, max_tokens: int | None = None) -> str:
        url = self.base_url + "/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        logger.info("llm request model=%s url_host=%s", self.model, _host(self.base_url))
        try:
            with httpx.Client(timeout=30, transport=self._transport) as client:
                response = client.post(
                    url,
                    headers={"Authorization": "Bearer " + self._api_key, "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise ValueError("模型服务不可达") from exc
        if response.status_code >= 400:
            raise ValueError(f"模型服务返回 {response.status_code}")
        body = response.json()
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("模型响应缺少 content") from exc


def normalize_generated_case(item: dict[str, Any]) -> dict[str, Any]:
    """把常见的模型输出收成校验器认识的顶层字段。已是规范形状时保持不变。"""

    request = item.get("request") if isinstance(item.get("request"), dict) else {}
    raw_method = item.get("method") or item.get("httpMethod") or request.get("method") or request.get("httpMethod") or ""
    raw_path = (
        item.get("relativePath")
        or item.get("path")
        or request.get("relativePath")
        or request.get("path")
        or request.get("url")
        or item.get("url")
        or ""
    )
    headers = item.get("headers") if isinstance(item.get("headers"), dict) else request.get("headers")
    query = item.get("query") if isinstance(item.get("query"), dict) else request.get("query") or request.get("params")
    path_params = item.get("pathParams") if isinstance(item.get("pathParams"), dict) else request.get("pathParams")
    if "body" in item:
        body = item.get("body")
    else:
        body = request.get("body")
    raw_assertions = item.get("assertions")
    if not isinstance(raw_assertions, list):
        raw_assertions = item.get("checks") if isinstance(item.get("checks"), list) else request.get("assertions")
    assertions = [_normalize_assertion(entry) for entry in raw_assertions or [] if isinstance(entry, dict)]
    try:
        timeout = int(item.get("timeout") or item.get("timeoutSeconds") or 30)
    except (TypeError, ValueError):
        timeout = 30
    normalized: dict[str, Any] = {
        "name": str(item.get("name") or item.get("title") or "未命名")[:200],
        "description": str(item.get("description") or ""),
        "scenario": str(item.get("scenario") or ""),
        "basis": str(item.get("basis") or item.get("reason") or ""),
        "method": str(raw_method).upper(),
        "relativePath": _path_only(str(raw_path)),
        "headers": headers if isinstance(headers, dict) else {},
        "query": query if isinstance(query, dict) else {},
        "pathParams": path_params if isinstance(path_params, dict) else {},
        "body": body,
        "timeout": timeout,
        "assertions": assertions,
        "origin": str(item.get("origin") or "llm"),
    }
    if item.get("extract") is not None:
        normalized["extract"] = item.get("extract")
    if item.get("dependencies") is not None:
        normalized["dependencies"] = item.get("dependencies")
    return normalized


def failure_details(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report.get("results") or []:
        if not isinstance(item, dict) or item.get("status") in {"passed", "skipped"}:
            continue
        request = item.get("request") if isinstance(item.get("request"), dict) else {}
        failed = []
        for assertion in item.get("assertionResults") or []:
            if isinstance(assertion, dict) and assertion.get("passed") is False:
                failed.append(
                    {
                        "type": assertion.get("type"),
                        "expected": assertion.get("expected"),
                        "actual": assertion.get("actual"),
                        "message": assertion.get("message"),
                    }
                )
        rows.append(
            {
                "name": item.get("name") or "",
                "method": item.get("method") or request.get("method"),
                "path": redact_secrets(str(item.get("path") or request.get("url") or ""))[:300],
                "responseStatus": item.get("responseStatus"),
                "errorClass": item.get("errorClass"),
                "errorMessage": redact_secrets(str(item.get("errorMessage") or ""))[:300],
                "failedAssertions": failed,
                "responseSnippet": redact_secrets(str(item.get("responseBody") or ""))[:500],
            }
        )
        if len(rows) >= 30:
            break
    return rows


def apply_triage(
    report: dict[str, Any],
    *,
    base_url: str,
    model: str,
    api_key: str,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, str]:
    try:
        message = LLMGenerationProvider(
            base_url=base_url,
            model=model,
            api_key=api_key,
            transport=transport,
        ).triage(report)
        return "succeeded", message
    except Exception as exc:
        reason = redact_secrets(f"{type(exc).__name__}: {exc}", secret=api_key)
        logger.warning("llm triage failed: %s", reason)
        return "failed", f"研判失败，数据报告仍可查看。原因：{reason}"[:2000]


def bound_model_text(text: str, limit: int = TRIAGE_CHAR_LIMIT) -> str:
    """超长时停在句号或换行处，并标明已截断。"""

    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    budget = limit - len(_TRUNCATION_MARK)
    if budget < 1:
        return _TRUNCATION_MARK[:limit]
    window = cleaned[:budget]
    cut = _last_boundary(window)
    if cut <= 0:
        cut = budget
    return window[:cut].rstrip() + _TRUNCATION_MARK


def _last_boundary(text: str) -> int:
    best = -1
    for index, char in enumerate(text):
        if char in "。！？；\n":
            best = index + 1
        elif char in ".!?;" and (index + 1 == len(text) or text[index + 1].isspace()):
            best = index + 1
    return best


def redact_secrets(text: str, *, secret: str | None = None) -> str:
    if secret:
        text = text.replace(secret, "***")
    text = _BEARER_RE.sub("Bearer ***", text)
    text = _SECRET_RE.sub("sk-***", text)
    return text


def intended_generation() -> tuple[str, str | None]:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.llm_api_key:
        return "llm", settings.llm_model
    return "mock", None


def provider_from_settings() -> Any:
    from app.core.config import get_settings
    from app.modules.ai.mock_provider import MockGenerationProvider

    settings = get_settings()
    if not settings.llm_api_key:
        return MockGenerationProvider()
    return LLMGenerationProvider(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
    )


def _unwrap_cases(parsed: Any) -> list[Any]:
    if isinstance(parsed, dict) and isinstance(parsed.get("cases"), list):
        return list(parsed["cases"])
    if isinstance(parsed, list):
        return parsed
    raise ValueError("模型输出不是用例数组")


def _normalize_assertion(raw: dict[str, Any]) -> dict[str, Any]:
    kind_raw = str(raw.get("type") or raw.get("assertionType") or "")
    compact = re.sub(r"[\s_\-]", "", kind_raw).lower()
    expected = raw.get("expected", raw["expect"] if "expect" in raw else raw.get("value"))
    path = raw.get("path") or raw.get("jsonPath") or raw.get("bodyPath") or raw.get("pointer")
    if isinstance(path, str) and path.startswith("$."):
        path = path[2:]
    out: dict[str, Any] = {}
    if path:
        out["path"] = path
    if compact in {"status", "statuscode", "httpstatus"}:
        out["type"] = "statusCode"
        if isinstance(expected, str) and expected.isdigit():
            expected = int(expected)
        if expected is None and raw.get("code") is not None:
            expected = raw.get("code")
        if expected is not None:
            out["expected"] = expected
        return out
    if compact in {"bodypath", "jsonpath", "jsontype"}:
        if isinstance(expected, str) and expected.lower() in JSON_KINDS:
            out["type"] = "jsonType"
            out["expected"] = expected.lower()
        else:
            out["type"] = "equals"
            if expected is not None:
                out["expected"] = expected
        return out
    if compact in {"equal", "equals", "eq"}:
        out["type"] = "equals"
        if expected is not None:
            out["expected"] = expected
        return out
    if compact in {"range", "between"}:
        out["type"] = "range"
        minimum = raw.get("minimum", raw.get("min"))
        maximum = raw.get("maximum", raw.get("max"))
        if minimum is not None:
            out["minimum"] = minimum
        if maximum is not None:
            out["maximum"] = maximum
        return out
    out["type"] = kind_raw
    if expected is not None and kind_raw != "range":
        out["expected"] = expected
    return out


def _path_only(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if "://" in text:
        text = urlsplit(text).path or "/"
    if "?" in text:
        text = text.split("?", 1)[0]
    return text


def _load_json(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def _host(url: str) -> str:
    return urlsplit(url).netloc
