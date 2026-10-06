from __future__ import annotations

import logging
import os
import sys

import pytest

from utils.db_query_logger import QueryLogger


@pytest.mark.skipif(sys.platform == "win32", reason="fork only")
def test_forked_child_restarts_flush_thread_and_writes_buffered_lines(tmp_path):
    out = tmp_path / "queries.log"
    logger = logging.getLogger("test_db_query_fork")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(logging.FileHandler(out))
    query_logger = QueryLogger(
        logger=logger,
        slow_logger=logging.getLogger("test_db_query_fork_slow"),
        slow_threshold_ms=10_000,
        flush_interval_seconds=0.05,
    )
    query_logger.start()

    pid = os.fork()
    if pid == 0:  # child: flush thread must be alive again and drain the buffer
        code = 1
        try:
            query_logger.record("SELECT 1", 1.0)
            for _ in range(100):
                for handler in logger.handlers:
                    handler.flush()
                if out.exists() and "SELECT 1" in out.read_text():
                    code = 0
                    break
                __import__("time").sleep(0.02)
        finally:
            os._exit(code)
    _, status = os.waitpid(pid, 0)
    query_logger.stop()

    assert os.waitstatus_to_exitcode(status) == 0


def test_record_attributes_query_to_the_calling_application_frame():
    lines = []
    logger = logging.getLogger("test_db_query_caller")
    query_logger = QueryLogger(
        logger=logger,
        slow_logger=logging.getLogger("test_db_query_caller_slow"),
        slow_threshold_ms=10_000,
        flush_interval_seconds=60,
    )
    logger.info = lines.append  # type: ignore[method-assign]

    query_logger.record("SELECT 1", 1.0)
    query_logger.flush()

    assert f"caller={__file__}:" in lines[0]
