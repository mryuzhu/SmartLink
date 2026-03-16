from __future__ import annotations

from types import SimpleNamespace

from smartlink.models import ExecutionResult
from smartlink.services.adb import ADBService


def build_service():
    class Logger:
        def info(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

    service = ADBService(Logger())
    service.is_available = lambda: True
    return service


def test_build_pair_target_and_validators():
    service = build_service()
    assert service.build_pair_target("192.168.1.10", 37121) == "192.168.1.10:37121"

    assert service.validate_pair_ip("192.168.1.10") is True
    assert service.validate_pair_ip("") is False
    assert service.validate_pair_ip("300.1.1.1") is False
    assert service.validate_pair_ip("abc") is False

    assert service.validate_pair_port("37121") is True
    assert service.validate_pair_port(5555) is True
    assert service.validate_pair_port("") is False
    assert service.validate_pair_port("abc") is False
    assert service.validate_pair_port("70000") is False

    assert service.validate_pair_code("123456") is True
    assert service.validate_pair_code("") is False
    assert service.validate_pair_code("12ab") is False


def test_pair_runs_pair_then_connect():
    service = build_service()
    calls: list[list[str]] = []

    def fake_run(args: list[str], timeout: int = 8):
        calls.append(args)
        if args[1] == "pair":
            return SimpleNamespace(returncode=0, stdout="paired", stderr="")
        return SimpleNamespace(returncode=0, stdout="connected", stderr="")

    service._run = fake_run
    result = service.pair("192.168.1.10", "37121", "123456", "5555")

    assert result.success is True
    assert calls == [
        ["adb", "pair", "192.168.1.10:37121", "123456"],
        ["adb", "connect", "192.168.1.10:5555"],
    ]


def test_pair_stops_when_pair_command_fails():
    service = build_service()
    calls: list[list[str]] = []

    def fake_run(args: list[str], timeout: int = 8):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout="", stderr="pair failed")

    service._run = fake_run
    result = service.pair("192.168.1.10", "37121", "123456")

    assert result.success is False
    assert result.error == "adb_pair_failed"
    assert calls == [["adb", "pair", "192.168.1.10:37121", "123456"]]


def test_pair_uses_default_debug_port():
    service = build_service()
    calls: list[list[str]] = []

    def fake_run(args: list[str], timeout: int = 8):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    service._run = fake_run
    result = service.pair("192.168.1.10", 37121, "123456")

    assert result.success is True
    assert calls[-1] == ["adb", "connect", "192.168.1.10:5555"]


def test_pair_rejects_invalid_values():
    service = build_service()

    invalid_ip = service.pair("bad-ip", 37121, "123456")
    invalid_port = service.pair("192.168.1.10", "99999", "123456")
    invalid_code = service.pair("192.168.1.10", 37121, "abc123")

    assert invalid_ip == ExecutionResult(False, "设备 IP 无效。", {}, "invalid_pair_ip")
    assert invalid_port == ExecutionResult(False, "配对端口无效。", {}, "invalid_pair_port")
    assert invalid_code == ExecutionResult(False, "配对码无效。", {}, "invalid_pair_code")
