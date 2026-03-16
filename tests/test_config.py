from __future__ import annotations

import json
from pathlib import Path

from smartlink.config import ConfigManager
from smartlink.models import ActionConfig


def test_config_read_write_roundtrip(tmp_path: Path):
    config_path = tmp_path / "launcher_config.json"
    manager = ConfigManager(config_path)
    settings = manager.update_settings({"api_token": "abc123", "adb_ip": "192.168.1.8:5555"})
    manager.upsert_action(
        ActionConfig(
            name="打开画图",
            type="exe",
            cmd="mspaint.exe",
            allow_api=True,
            category="办公",
        )
    )

    reloaded = ConfigManager(config_path)
    actions = reloaded.list_actions()

    assert settings.api_token == "abc123"
    assert reloaded.get_settings().adb_ip == "192.168.1.8:5555"
    assert any(action.name == "打开画图" for action in actions)


def test_legacy_config_is_migrated(tmp_path: Path):
    config_path = tmp_path / "legacy.json"
    legacy_payload = {
        "_adb_ip": "192.168.1.6:5555",
        "旧动作": {"type": "exe", "cmd": "notepad.exe"},
    }
    config_path.write_text(json.dumps(legacy_payload, ensure_ascii=False), encoding="utf-8")

    manager = ConfigManager(config_path)

    assert manager.get_settings().adb_ip == "192.168.1.6:5555"
    assert manager.get_action("旧动作") is not None
    payload = manager.load()
    assert payload["version"] == 2
    assert "settings" in payload and "actions" in payload
