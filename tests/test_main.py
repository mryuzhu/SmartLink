from smartlink.main import resolve_access_host


def test_resolve_access_host_keeps_localhost() -> None:
    assert resolve_access_host("127.0.0.1") == "127.0.0.1"


def test_resolve_access_host_uses_lan_for_wildcard(monkeypatch) -> None:
    monkeypatch.setattr("smartlink.main.get_lan_addresses", lambda: ["127.0.0.1", "192.168.1.248"])
    assert resolve_access_host("0.0.0.0") == "192.168.1.248"  # noqa: S104 - 测试通配监听配置
