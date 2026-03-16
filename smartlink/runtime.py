from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import current_app


@dataclass(slots=True)
class AppPaths:
    root: Path
    config_file: Path
    log_file: Path


@dataclass(slots=True)
class AppState:
    paths: AppPaths
    logger: logging.Logger
    config_manager: Any
    action_service: Any
    adb_service: Any
    system_service: Any
    integration_manager: Any
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    request_history: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))

    def record_request(self, record: dict[str, Any]) -> None:
        self.request_history.appendleft(record)


def get_state() -> AppState:
    return current_app.extensions["smartlink"]
