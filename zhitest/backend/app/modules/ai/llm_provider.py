"""OpenAI 兼容的生成与研判。

默认指向 DeepSeek。密钥只从环境变量读取，不写入日志。
没有密钥时调用方应继续使用 Mock，而不是在这里编造结果。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger("zhitest.llm")


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
            "rules": [
                "只根据给定契约生成用例",
                "契约没有声明 401 时不要生成 401",
                "每条用例必须有 assertions",
                "输出 JSON 数组，不要输出解释",
            ],
        }
        content = self._chat(
            "你是测试用例生成器。只输出 JSON 数组。",
            json.dumps(prompt, ensure_ascii=False),
        )
        parsed = _load_json(content)
        if isinstance(parsed, dict) and isinstance(parsed.get("cases"), list):
            parsed = parsed["cases"]
        if not isinstance(parsed, list):
            raise ValueError("模型输出不是用例数组")
        for item in parsed:
            if isinstance(item, dict):
                item["origin"] = "llm"
        return parsed

    def triage(self, report: dict[str, Any]) -> str:
        content = self._chat(
            "你只根据给定执行结果写数据摘要。不要把未验证的问题说成已确认漏洞。输出一段中文。",
            json.dumps(
                {
                    "status": report.get("status"),
                    "passed": report.get("passedCount"),
                    "assertionFailed": report.get("assertionFailedCount"),
                    "passRateText": report.get("passRateText"),
                },
                ensure_ascii=False,
            ),
        )
        return content.strip()[:2000]

    def _chat(self, system: str, user: str) -> str:
        url = self.base_url + "/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
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


def _load_json(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


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


def _host(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).netloc
