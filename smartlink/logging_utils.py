from __future__ import annotations

import logging
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("smartlink")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(handler)
    logger.addHandler(console)
    logger.propagate = False
    return logger


def tail_log(log_path: Path, limit: int = 50) -> list[str]:
    if not log_path.exists():
        return []
    with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
        return list(deque(handle, maxlen=limit))
