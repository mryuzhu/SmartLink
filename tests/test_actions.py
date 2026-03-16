from __future__ import annotations

from pathlib import Path

from smartlink import create_app


def test_action_validation_rules(tmp_path: Path):
    app = create_app(config_path=tmp_path / "launcher_config.json", testing=True)
    service = app.extensions["smartlink"].action_service

    ok, errors, _action = service.save_action(
        {
            "name": "非法 ADB",
            "type": "adb",
            "cmd": "echo hello",
            "allow_api": True,
            "enabled": True,
        }
    )
    assert not ok
    assert any("adb" in error.lower() for error in errors)

    ok, errors, _action = service.save_action(
        {
            "name": "非法亮度",
            "type": "brightness",
            "cmd": "brightness 50",
            "allow_api": True,
            "enabled": True,
        }
    )
    assert not ok
    assert any("XXX" in error for error in errors)


def test_action_list_reading(app):
    actions = app.extensions["smartlink"].action_service.list_actions()
    names = {action.name for action in actions}
    assert "打开记事本" in names
    assert "私有动作" in names
