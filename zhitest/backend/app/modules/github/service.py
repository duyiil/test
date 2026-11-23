"""GitHub 项目接入：给出仓库网址，检测项目并定位接口定义。

只允许 github.com 主机的公开仓库 URL，其余主机一律拒绝（含内网地址）。
未配置 ZHITEST_GITHUB_TOKEN 时走 GitHub 匿名 API（限流 60 次/小时，
限流时提示配置令牌）。抓取内容只用于解析 OpenAPI，不落盘、不执行。
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings
from app.core.errors import AppError

logger = logging.getLogger("zhitest.github")

GITHUB_HOSTS = {"github.com", "www.github.com"}
API_BASE = "https://api.github.com"
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
MAX_TREE_FILES = 2000

_URL_RE = re.compile(
    r"^https?://(?P<host>[^/]+)/(?P<owner>[^/]+)/(?P<repo>[^/]+)"
    r"(?:/(?P<kind>tree|blob)/(?P<ref>[^/]+)(?P<path>/.*)?)?/?$"
)

# 常见的接口定义文件名与位置（大小写不敏感）
SPEC_NAMES = {
    "openapi.json",
    "openapi.yaml",
    "openapi.yml",
    "swagger.json",
    "swagger.yaml",
    "swagger.yml",
}
SPEC_DIRS = ("", "docs/", "api/", "openapi/", "swagger/", "static/")

# 简单框架指纹：文件名 -> (语言, 框架)
FRAMEWORK_MARKERS = [
    ({"pom.xml", "build.gradle"}, "Java", "Spring Boot / JVM"),
    ({"package.json", "vite.config.ts", "next.config.js"}, "TypeScript", "Node.js 前端/全栈"),
    ({"pyproject.toml", "requirements.txt", "Pipfile"}, "Python", "Python"),
    ({"go.mod"}, "Go", "Go"),
]


def parse_github_url(url: str) -> dict[str, str]:
    """严格解析仓库 URL。只接受 github.com 主机。"""

    text = (url or "").strip()
    if not text:
        raise AppError(422, "VALIDATION_ERROR", "请输入 GitHub 仓库网址")
    match = _URL_RE.match(text)
    if match is None or match.group("host").lower() not in GITHUB_HOSTS:
        raise AppError(422, "VALIDATION_ERROR", "只支持 github.com 的仓库网址")
    return {
        "owner": match.group("owner"),
        "repo": match.group("repo"),
        "ref": match.group("ref") or "",
        "path": (match.group("path") or "").lstrip("/"),
    }


def _client() -> httpx.Client:
    settings = get_settings()
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if settings.github_token:
        headers["Authorization"] = "Bearer " + settings.github_token
    # 不走宿主系统代理（部分机器上系统代理无法路由 api.github.com），
    # 需要代理时显式配置 ZHITEST_GITHUB_PROXY。
    proxy = settings.github_proxy or None
    return httpx.Client(timeout=15, headers=headers, trust_env=False, proxy=proxy)


def _check_response(response: httpx.Response) -> None:
    if response.status_code == 404:
        raise AppError(404, "NOT_FOUND", "仓库不存在、已私有化或分支不存在")
    if response.status_code in {403, 429}:
        raise AppError(
            429,
            "RATE_LIMITED",
            "GitHub API 限流（匿名 60 次/小时）。可在环境变量 ZHITEST_GITHUB_TOKEN 配置令牌后重试",
        )
    if response.status_code >= 400:
        raise AppError(502, "UPSTREAM_ERROR", f"GitHub API 返回 {response.status_code}")


def _get_json(client: httpx.Client, path: str) -> dict[str, Any]:
    try:
        response = client.get(API_BASE + path)
    except httpx.HTTPError as exc:
        raise AppError(502, "UPSTREAM_ERROR", f"访问 GitHub 失败：{type(exc).__name__}") from exc
    _check_response(response)
    return response.json()


def repo_meta(owner: str, repo: str) -> dict[str, Any]:
    with _client() as client:
        data = _get_json(client, f"/repos/{owner}/{repo}")
    return {
        "fullName": str(data.get("full_name") or f"{owner}/{repo}"),
        "description": str(data.get("description") or ""),
        "language": str(data.get("language") or ""),
        "defaultBranch": str(data.get("default_branch") or "main"),
        "stars": int(data.get("stargazers_count") or 0),
        "htmlUrl": str(data.get("html_url") or ""),
    }


def repo_tree(owner: str, repo: str, ref: str) -> list[str]:
    with _client() as client:
        data = _get_json(client, f"/repos/{owner}/{repo}/git/trees/{ref}?recursive=1")
    if data.get("truncated"):
        logger.warning("github tree truncated for %s/%s", owner, repo)
    paths: list[str] = []
    for item in data.get("tree") or []:
        if item.get("type") == "blob":
            name = str(item.get("path") or "")
            if name:
                paths.append(name)
        if len(paths) >= MAX_TREE_FILES:
            break
    return paths


def spec_candidates(paths: list[str]) -> list[str]:
    lowered = {p.lower(): p for p in paths}
    candidates: list[str] = []
    for directory in SPEC_DIRS:
        for name in SPEC_NAMES:
            key = (directory + name).lower()
            if key in lowered:
                candidates.append(lowered[key])
    # 兜底：任何目录下名为 openapi/swagger 的文件
    for path in paths:
        filename = path.split("/")[-1].lower()
        if filename in SPEC_NAMES and path not in candidates:
            candidates.append(path)
    return candidates


def detect_frameworks(paths: list[str]) -> list[str]:
    names = {p.split("/")[-1].lower() for p in paths}
    found: list[str] = []
    for markers, language, label in FRAMEWORK_MARKERS:
        if markers & names:
            found.append(f"{language} / {label}")
    return found or ["未识别（按通用 HTTP 服务处理）"]


def fetch_file(owner: str, repo: str, ref: str, path: str) -> str:
    """通过 contents API 读取文件内容（base64 返回），不依赖 raw 域名。"""

    import base64

    with _client() as client:
        data = _get_json(client, f"/repos/{owner}/{repo}/contents/{path}?ref={ref}")
    if str(data.get("encoding") or "") != "base64" or data.get("content") is None:
        raise AppError(422, "VALIDATION_ERROR", f"{path} 不是可读取的文本文件")
    if int(data.get("size") or 0) > MAX_FILE_SIZE:
        raise AppError(422, "VALIDATION_ERROR", f"文件超过 {MAX_FILE_SIZE // 1024 // 1024}MB，拒绝解析")
    content = base64.b64decode(data["content"])
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AppError(422, "VALIDATION_ERROR", "文件不是 UTF-8 文本") from exc


def detect_project(url: str) -> dict[str, Any]:
    """检测 GitHub 项目：仓库信息、语言/框架指纹、候选接口定义。"""

    parsed = parse_github_url(url)
    owner, repo = parsed["owner"], parsed["repo"]
    meta = repo_meta(owner, repo)
    ref = parsed["ref"] or meta["defaultBranch"]
    paths = repo_tree(owner, repo, ref)

    from app.modules.ai.openapi_parser import parse_openapi_document

    candidates: list[dict[str, Any]] = []
    for path in spec_candidates(paths):
        entry: dict[str, Any] = {"path": path, "parseOk": False, "endpointCount": 0, "error": ""}
        try:
            raw = fetch_file(owner, repo, ref, path)
            parsed_doc = parse_openapi_document(raw)
            entry["parseOk"] = True
            entry["endpointCount"] = len(parsed_doc["endpoints"])
            entry["openapi"] = parsed_doc["openapi"]
        except AppError as exc:
            entry["error"] = exc.message
        except ValueError as exc:
            entry["error"] = str(exc)
        candidates.append(entry)

    return {
        "url": url,
        "repo": meta,
        "ref": ref,
        "fileCount": len(paths),
        "frameworks": detect_frameworks(paths),
        "specCandidates": candidates,
    }


def import_spec(db: Any, user: Any, project_id: Any, url: str, spec_path: str, ip: str | None) -> dict[str, Any]:
    """下载指定路径的接口定义并导入项目（复用 OpenAPI 确认链路）。"""

    parsed = parse_github_url(url)
    meta = repo_meta(parsed["owner"], parsed["repo"])
    ref = parsed["ref"] or meta["defaultBranch"]
    raw = fetch_file(parsed["owner"], parsed["repo"], ref, spec_path)
    from app.modules.platform.service import confirm_openapi

    return confirm_openapi(db, user, project_id, raw, ip)
