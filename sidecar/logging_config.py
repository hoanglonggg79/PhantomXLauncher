from __future__ import annotations

import inspect
import logging
import sys
from pathlib import Path

from loguru import logger

APP_NAME = "PhantomX"
APP_AUTHOR = "PhantomXTeam"

_STDLIB_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "asyncio", "fastapi")

_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{name}:{function}:{line} | {message}"
)
_STDERR_FORMAT = "{level: <8} | {message}"


def get_base_dir() -> Path:
    """
    Storage root, delegated to the shared resolver (GLOBAL RULE 2): portable.txt
    beside the executable wins, otherwise %LOCALAPPDATA%/PhantomXTeam/PhantomX.
    Kept as a thin wrapper because older callers import it from here.
    """
    from sidecar.utils.path_resolver import get_base_dir as resolve

    return resolve()


def get_log_dir() -> Path:
    log_dir = get_base_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_file() -> Path:
    return get_log_dir() / "sidecar.log"


class _InterceptHandler(logging.Handler):
    """
    Forward stdlib logging records into loguru. Without this, uvicorn runs with
    log_config=None and no handlers, so unhandled ASGI exceptions vanish.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def intercept_stdlib_logging() -> None:
    handler = _InterceptHandler()
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)
    for name in _STDLIB_LOGGERS:
        std = logging.getLogger(name)
        std.handlers = [handler]
        std.propagate = False


def configure_logging() -> Path:
    """
    Route loguru to the storage-root log file plus stderr. NEVER stdout: stdout is
    reserved for the PHANTOMX_READY handshake.
    """
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    log_file = get_log_file()

    logger.remove()
    logger.add(
        log_file,
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        enqueue=True,
        format=_FILE_FORMAT,
    )
    if sys.stderr is not None:
        logger.add(sys.stderr, level="INFO", colorize=False, format=_STDERR_FORMAT)

    intercept_stdlib_logging()

    return log_file
