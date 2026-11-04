from __future__ import annotations

import logging

from app.core.request_context import get_request_id


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def setup_logging(level: str) -> None:
    root = logging.getLogger()
    if getattr(root, "_zhitest_configured", False):
        root.setLevel(level)
        return
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)
    setattr(root, "_zhitest_configured", True)
