"""网站检测：扫描真实网页并探测接口定义。

给出一个公网网址，抓取首页并记录状态、重定向链、响应头、技术栈指纹、
安全响应头与探测路径状态码，同时探测常见位置的 OpenAPI/Swagger 文档。
所有出站请求都经过 SSRF 检查（默认只允许公网地址），不落盘、不执行。

代理复用 ZHITEST_GITHUB_PROXY（名称沿用，避免新增配置）。
"""

from __future__ import annotations

import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.errors import AppError
from app.execution.ssrf import assert_target_allowed
from app.models.platform import ProjectEnvironment
from app.models.user import User
from app.modules.audit.service import write_audit
from app.modules.platform.service import confirm_openapi, get_owned_project
from app.modules.projects.service import validate_base_url

logger = logging.getLogger("zhitest.site")

MAX_FILE_SIZE = 2 * 1024 * 1024  # 规格文件 2MB 上限（与 GitHub 模块一致）
MAX_PAGE_BYTES = 256 * 1024  # 首页正文读取上限
MAX_REDIRECTS = 5
REQUEST_TIMEOUT = 10.0
PROBE_WORKERS = 5

SPEC_PATHS = (
    "/openapi.json",
    "/openapi.yaml",
    "/swagger.json",
    "/swagger.yaml",
    "/api/openapi.json",
    "/api/swagger.json",
    "/api-docs",
    "/v1/openapi.json",
    "/v1/swagger.json",
    "/v2/swagger.json",
    "/v3/api-docs",
    "/api/v3/openapi.json",
    "/swagger/v1/swagger.json",
)
PROBE_PATHS = ("/robots.txt", "/sitemap.xml", "/health", "/api/health")

SECURITY_HEADERS = (
    "Strict-Transport-Security",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Content-Security-Policy",
    "Referrer-Policy",
    "Permissions-Policy",
)

# 响应头 -> 技术标签
HEADER_TECH = ("x-powered-by", "server", "x-generator", "x-aspnet-version")
# (子串或正则, 标签) — 正文指纹。子串一律小写，与 body.lower() 比对
BODY_TECH = (
    (re.compile(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)', re.I), "Generator"),
    ("wp-content", "WordPress"),
    ("__next_data__", "Next.js"),
    ("data-reactroot", "React"),
    ("vue", "Vue"),
    ("drupal", "Drupal"),
    ("asp.net", "ASP.NET"),
    ("shopify", "Shopify"),
    ("/wp-json", "WordPress REST"),
)

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_site_url(url: str) -> str:
    """校验并归一化站点地址。只接受 http/https 且通过 SSRF 检查的目标。"""

    text = (url or "").strip()
    if not text:
        raise AppError(422, "VALIDATION_ERROR", "请输入网站地址")
    if len(text) > 500:
        raise AppError(422, "VALIDATION_ERROR", "地址过长")
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"}:
        raise AppError(422, "VALIDATION_ERROR", "仅支持 http 或 https 地址")
    if parts.username or parts.password:
        raise AppError(422, "VALIDATION_ERROR", "地址不能包含用户名或密码")
    if not parts.hostname:
        raise AppError(422, "VALIDATION_ERROR", "地址缺少主机名")
    normalized = f"{parts.scheme}://{parts.netloc}/"
    assert_target_allowed(normalized)
    return normalized


def _client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=False,
        # 不走宿主系统代理（与执行器一致），需要时显式配置 ZHITEST_GITHUB_PROXY
        trust_env=False,
        proxy=settings.github_proxy or None,
        transport=transport,
    )


def _follow_redirects(
    client: httpx.Client, start_url: str
) -> tuple[httpx.Response, list[dict[str, Any]]]:
    """手动跟随重定向，逐跳 SSRF 检查并记录链路。"""

    current = start_url
    chain: list[dict[str, Any]] = []
    for _ in range(MAX_REDIRECTS + 1):
        assert_target_allowed(current)
        try:
            response = client.get(current)
        except httpx.HTTPError as exc:
            raise AppError(502, "UPSTREAM_ERROR", f"访问站点失败：{type(exc).__name__}") from exc
        if response.status_code in {301, 302, 303, 307, 308} and response.headers.get("location"):
            target = urljoin(current, response.headers["location"])
            try:
                assert_target_allowed(target)
            except AppError as exc:
                raise AppError(403, "SSRF_BLOCKED", f"重定向目标被拒绝：{exc.message}") from exc
            chain.append({"from": current, "to": target, "status": response.status_code})
            current = target
            continue
        return response, chain
    raise AppError(422, "VALIDATION_ERROR", f"重定向超过 {MAX_REDIRECTS} 次")


def _fetch_quiet(client: httpx.Client, url: str) -> httpx.Response | None:
    try:
        assert_target_allowed(url)
        return client.get(url)
    except (httpx.HTTPError, AppError):
        return None


def _text(response: httpx.Response, cap: int) -> str:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes(chunk_size=65536):
        chunks.append(chunk)
        size += len(chunk)
        if size >= cap:
            break
    return b"".join(chunks)[:cap].decode("utf-8", errors="replace")


def detect_site(url: str, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    normalized = parse_site_url(url)
    with _client(transport) as client:
        response, chain = _follow_redirects(client, normalized)
        final_url = str(response.url)
        body = _text(response, MAX_PAGE_BYTES) if response.status_code < 400 else ""

        title_match = _TITLE_RE.search(body)
        title = _TAG_RE.sub("", title_match.group(1)).strip()[:200] if title_match else ""

        technologies: list[str] = []
        for name in HEADER_TECH:
            value = response.headers.get(name)
            if value:
                technologies.append(f"{name}: {value}")
        for marker, label in BODY_TECH:
            if isinstance(marker, re.Pattern):
                if marker.search(body):
                    technologies.append(label)
            elif marker in body.lower():
                technologies.append(label)
        unique_tech: list[str] = []
        for item in technologies:
            if item not in unique_tech:
                unique_tech.append(item)
        if not unique_tech:
            unique_tech = ["未识别"]

        headers_lower = {key.lower() for key in response.headers}
        security_headers = [
            {"name": name, "present": name.lower() in headers_lower} for name in SECURITY_HEADERS
        ]

        probe_results: list[dict[str, Any]] = []
        for path in PROBE_PATHS:
            probe = _fetch_quiet(client, urljoin(final_url, path))
            probe_results.append({"path": path, "status": probe.status_code if probe is not None else None})

        candidates = _probe_specs(client, final_url)
    return {
        "url": normalized,
        "finalUrl": final_url,
        "status": response.status_code,
        "title": title,
        "redirects": chain,
        "technologies": unique_tech,
        "securityHeaders": security_headers,
        "probeResults": probe_results,
        "specCandidates": candidates,
    }


def _probe_specs(client: httpx.Client, base_url: str) -> list[dict[str, Any]]:
    from app.modules.ai.openapi_parser import parse_openapi_document

    def probe(path: str) -> dict[str, Any]:
        entry: dict[str, Any] = {"path": path, "status": None, "parseOk": False, "endpointCount": 0, "error": ""}
        response = _fetch_quiet(client, urljoin(base_url, path))
        if response is None:
            entry["error"] = "请求失败"
            return entry
        entry["status"] = response.status_code
        if response.status_code >= 400:
            entry["error"] = f"HTTP {response.status_code}"
            return entry
        content_type = str(response.headers.get("content-type") or "").lower()
        if "text/html" in content_type:
            entry["error"] = "返回的不是 JSON/YAML（text/html）"
            return entry
        if int(response.headers.get("content-length") or 0) > MAX_FILE_SIZE:
            entry["error"] = "文件超过 2MB，拒绝解析"
            return entry
        raw = _text(response, MAX_FILE_SIZE + 1)
        if len(raw.encode("utf-8", errors="replace")) > MAX_FILE_SIZE:
            entry["error"] = "文件超过 2MB，拒绝解析"
            return entry
        try:
            parsed = parse_openapi_document(raw)
            entry["parseOk"] = True
            entry["endpointCount"] = len(parsed["endpoints"])
            entry["openapi"] = parsed["openapi"]
        except ValueError as exc:
            entry["error"] = str(exc)
        return entry

    with ThreadPoolExecutor(max_workers=PROBE_WORKERS) as pool:
        return list(pool.map(probe, SPEC_PATHS))


def _scan_summary(detection: dict[str, Any]) -> dict[str, Any]:
    """精简持久化摘要：不带候选与重定向链，控制快照体积。"""

    return {
        "url": detection["url"],
        "finalUrl": detection["finalUrl"],
        "status": detection["status"],
        "title": detection["title"],
        "technologies": detection["technologies"],
        "securityHeaders": detection["securityHeaders"],
        "probeResults": detection["probeResults"],
        "scannedAt": utcnow().isoformat(),
    }


def _fetch_spec(client: httpx.Client, base_url: str, spec_path: str) -> str:
    target = urljoin(base_url, "/" + spec_path.lstrip("/"))
    assert_target_allowed(target)
    try:
        response = client.get(target)
    except httpx.HTTPError as exc:
        raise AppError(502, "UPSTREAM_ERROR", f"拉取接口定义失败：{type(exc).__name__}") from exc
    if response.status_code >= 400:
        raise AppError(422, "VALIDATION_ERROR", f"接口定义返回 HTTP {response.status_code}")
    if int(response.headers.get("content-length") or 0) > MAX_FILE_SIZE:
        raise AppError(422, "VALIDATION_ERROR", f"文件超过 {MAX_FILE_SIZE // 1024 // 1024}MB，拒绝解析")
    raw = _text(response, MAX_FILE_SIZE + 1)
    if len(raw.encode("utf-8", errors="replace")) > MAX_FILE_SIZE:
        raise AppError(422, "VALIDATION_ERROR", f"文件超过 {MAX_FILE_SIZE // 1024 // 1024}MB，拒绝解析")
    return raw


def import_site_spec(
    db: Session,
    user: User,
    project_id: uuid.UUID,
    url: str,
    spec_path: str,
    *,
    ip: str | None,
    update_base_url: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """检测站点、拉取接口定义并导入项目；可选把执行目标更新为站点地址。"""

    project = get_owned_project(db, user, project_id)
    detection = detect_site(url, transport)
    with _client(transport) as client:
        raw = _fetch_spec(client, detection["finalUrl"], spec_path)
    result = confirm_openapi(db, user, project_id, raw, ip)
    project.site_scan = _scan_summary(detection)

    base_url_updated = False
    if update_base_url and detection["finalUrl"] != project.base_url:
        try:
            final = validate_base_url(detection["finalUrl"])
        except ValueError as exc:
            raise AppError(422, "VALIDATION_ERROR", str(exc)) from exc
        project.base_url = final
        # 活动环境会覆盖 base_url，一并停用，保证执行打的是检测站点
        db.execute(
            update(ProjectEnvironment)
            .where(ProjectEnvironment.project_id == project.id, ProjectEnvironment.is_active.is_(True))
            .values(is_active=False)
        )
        base_url_updated = True

    write_audit(
        db,
        action="site.import",
        actor_id=user.id,
        resource_type="project",
        resource_id=str(project.id),
        detail={
            "url": detection["url"],
            "finalUrl": detection["finalUrl"],
            "saved": result["saved"],
            "baseUrlUpdated": base_url_updated,
        },
        ip=ip,
    )
    return {**result, "scan": project.site_scan, "baseUrlUpdated": base_url_updated}
