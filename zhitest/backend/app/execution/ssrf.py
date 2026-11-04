"""出站地址检查。

默认允许公网地址。回环、链路本地、元数据地址和私网必须出现在显式允许名单里才放行。
演示服务使用 127.0.0.1，靠 ZHITEST_TARGET_ALLOWLIST 放行，不是关闭检查。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.errors import AppError

_METADATA_HOSTS = {"metadata.google.internal"}


def _allowlist() -> set[str]:
    raw = get_settings().target_allowlist
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _blocked_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return True
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def _resolve(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AppError(403, "SSRF_BLOCKED", f"无法解析目标主机 {host}") from exc
    addresses = []
    for info in infos:
        ip = info[4][0]
        addresses.append(ip.split("%")[0])
    if not addresses:
        raise AppError(403, "SSRF_BLOCKED", f"目标主机 {host} 没有解析结果")
    return addresses


def assert_target_allowed(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise AppError(403, "SSRF_BLOCKED", "只允许 http 或 https 目标")
    host = parts.hostname.lower()
    if host in _METADATA_HOSTS:
        raise AppError(403, "SSRF_BLOCKED", "拒绝访问元数据地址")
    if host in _allowlist():
        return
    port = parts.port or (443 if parts.scheme == "https" else 80)
    literal = None
    try:
        literal = str(ipaddress.ip_address(host))
    except ValueError:
        literal = None
    addresses = [literal] if literal else _resolve(host, port)
    for address in addresses:
        if _blocked_ip(address) or address == "169.254.169.254":
            raise AppError(403, "SSRF_BLOCKED", "目标解析到私网、回环、链路本地或元数据地址，已拒绝")


def assert_base_url_allowed(base_url: str) -> None:
    assert_target_allowed(base_url)
