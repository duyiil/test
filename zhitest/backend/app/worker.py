"""独立 Worker：轮询生成任务和执行任务。

不使用 Celery。任务状态在 PostgreSQL 里，Phase 2 没有 Redis。
本进程只发 HTTP 测试，不执行用户源码。
"""

from __future__ import annotations

import logging
import socket
import time

from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.execution.runner import execute_run
from app.modules.testing.service import claim_generation_task, claim_run, process_generation_task

logger = logging.getLogger("zhitest.worker")


def tick(worker_id: str) -> bool:
    db = SessionLocal()
    try:
        from app.modules.platform.service import recover_stale_runs

        recover_stale_runs(db)
        db.commit()
    finally:
        db.close()
    db = SessionLocal()
    try:
        task_id = claim_generation_task(db)
    finally:
        db.close()
    if task_id is not None:
        db = SessionLocal()
        try:
            process_generation_task(db, task_id)
        finally:
            db.close()
        return True
    db = SessionLocal()
    try:
        run_id = claim_run(db, worker_id)
    finally:
        db.close()
    if run_id is None:
        return False
    db = SessionLocal()
    try:
        execute_run(db, run_id)
    except Exception:
        logger.exception("run %s failed", run_id)
        _mark_run_failed(run_id)
    finally:
        db.close()
    return True


def _mark_run_failed(run_id: object) -> None:
    from datetime import datetime, timezone

    from app.models.testing import TestRun
    from app.modules.testing.service import _write_report

    db = SessionLocal()
    try:
        run = db.get(TestRun, run_id)
        if run is None or run.status in {"succeeded", "failed", "aborted", "cancelled"}:
            return
        run.status = "failed"
        run.abort_reason = "Worker 执行故障，已保留已完成的结果"
        run.finished_at = datetime.now(timezone.utc)
        _write_report(db, run)
        db.commit()
    finally:
        db.close()


def main() -> None:
    setup_logging("INFO")
    worker_id = socket.gethostname()
    logger.info("worker %s started", worker_id)
    while True:
        worked = tick(worker_id)
        if not worked:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
