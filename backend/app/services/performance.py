"""Timings visible with Uvicorn's normal console logging configuration."""

from contextlib import contextmanager
import logging
from time import perf_counter


logger = logging.getLogger("uvicorn.error.performance")


@contextmanager
def timed_stage(stage: str, **context):
    started = perf_counter()
    outcome = "ok"
    try:
        yield
    except BaseException:
        outcome = "error"
        raise
    finally:
        logger.info(
            "stage=%s outcome=%s duration_ms=%.2f context=%s",
            stage, outcome, (perf_counter() - started) * 1000, context,
        )
