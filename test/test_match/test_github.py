"""GitHub 项目接入：URL 解析、候选文件发现与框架指纹（纯本地，无网络）。

对应测试用例 TCM-GITHUB-001 ~ 006，见本目录 README。
"""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.modules.github.service import detect_frameworks, parse_github_url, spec_candidates


def test_parse_plain_repo_url() -> None:
    """TCM-GITHUB-001：普通仓库网址解析出 owner/repo。"""

    parsed = parse_github_url("https://github.com/swagger-api/swagger-petstore")
    assert parsed["owner"] == "swagger-api"
    assert parsed["repo"] == "swagger-petstore"
    assert parsed["ref"] == ""
    assert parsed["path"] == ""


def test_parse_branch_url() -> None:
    """TCM-GITHUB-002：带分支/路径的网址解析出 ref 与 path。"""

    parsed = parse_github_url("https://github.com/owner/repo/tree/dev/docs")
    assert parsed["owner"] == "owner"
    assert parsed["repo"] == "repo"
    assert parsed["ref"] == "dev"
    assert parsed["path"] == "docs"


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/owner/repo",
        "https://evil.com/owner/repo",
        "http://127.0.0.1/owner/repo",
        "https://github.com/",
        "not a url",
        "",
    ],
)
def test_reject_non_github_urls(url: str) -> None:
    """TCM-GITHUB-003：非 github.com 主机与非法格式一律拒绝（防 SSRF）。"""

    with pytest.raises(AppError):
        parse_github_url(url)


def test_spec_candidates_common_locations() -> None:
    """TCM-GITHUB-004：常见位置的 openapi/swagger 文件被发现。"""

    paths = ["README.md", "src/main.py", "openapi.yaml", "docs/swagger.json", "api/openapi.yml"]
    found = spec_candidates(paths)
    assert "openapi.yaml" in found
    assert "docs/swagger.json" in found
    assert "api/openapi.yml" in found


def test_spec_candidates_deep_fallback() -> None:
    """TCM-GITHUB-005：任意深度的 openapi 文件也能被发现。"""

    paths = ["src/main/resources/openapi.yaml", "pom.xml"]
    found = spec_candidates(paths)
    assert "src/main/resources/openapi.yaml" in found


def test_framework_detection() -> None:
    """TCM-GITHUB-006：按文件指纹识别语言/框架，无指纹时给出通用回退。"""

    assert detect_frameworks(["pom.xml", "src/main/java/A.java"]) == ["Java / Spring Boot / JVM"]
    assert detect_frameworks(["pyproject.toml", "app/main.py"]) == ["Python / Python"]
    assert detect_frameworks(["README.md"]) == ["未识别（按通用 HTTP 服务处理）"]
