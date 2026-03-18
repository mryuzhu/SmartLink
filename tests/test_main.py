from __future__ import annotations

from types import SimpleNamespace

from smartlink.main import resolve_access_host, start_adb_initializer


def test_resolve_access_host_keeps_localhost() -> None:
    assert resolve_access_host("127.0.0.1") == "127.0.0.1"


def test_resolve_access_host_uses_lan_for_wildcard(monkeypatch) -> None:
    monkeypatch.setattr("smartlink.main.get_lan_addresses", lambda: ["127.0.0.1", "192.168.1.248"])
    assert resolve_access_host("0.0.0.0") == "192.168.1.248"  # noqa: S104 - test wildcard host


def test_start_adb_initializer_runs_in_background(monkeypatch) -> None:
    calls: list[SimpleNamespace] = []

    class Logger:
        def info(self, *_args, **_kwargs):
            return None

        def error(self, *_args, **_kwargs):
            return None

    state = SimpleNamespace(
        logger=Logger(),
        adb_service=SimpleNamespace(
            connect_if_needed=lambda settings: calls.append(settings)
            or SimpleNamespace(success=True, message="ok")
        ),
    )
    settings = SimpleNamespace(enable_adb_connect=True, adb_ip="192.168.1.175")

    monkeypatch.setattr("smartlink.main.time.sleep", lambda _seconds: None)
    thread = start_adb_initializer(state, settings)
    thread.join(timeout=1)

    assert calls == [settings]
