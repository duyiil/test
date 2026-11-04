"""可替换的当前时间。测试用 monkeypatch，不是墙钟等待。"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
