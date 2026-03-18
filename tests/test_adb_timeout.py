from __future__ import annotations

import subprocess

from smartlink.services.adb import ADBService


class Logger:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None


def build_service() -> ADBService:
    service = ADBService(Logger())
    service.is_available = lambda: True
    return service


def test_connect_timeout_returns_failure(monkeypatch) -> None:
    service = build_service()

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["adb", "connect", "192.168.1.175"], timeout=5)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = service.connect("192.168.1.175")

    assert result.success is False
    assert result.message == "adb connect timeout"
    assert result.error == "timeout"


def test_connect_if_needed_does_not_raise_on_timeout(monkeypatch) -> None:
    service = build_service()

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["adb", "connect", "192.168.1.175"], timeout=5)

    monkeypatch.setattr(subprocess, "run", fake_run)
    settings = type(
        "Settings",
        (),
        {"enable_adb_connect": True, "adb_ip": "192.168.1.175"},
    )()

    result = service.connect_if_needed(settings)

    assert result.success is False
    assert result.error == "timeout"
