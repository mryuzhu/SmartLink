from __future__ import annotations

from pathlib import Path

import pytest

from smartlink import create_app
from smartlink.models import ActionConfig, ExecutionResult


@pytest.fixture()
def app(tmp_path: Path):
    config_path = tmp_path / "launcher_config.json"
    app = create_app(config_path=config_path, testing=True)
    state = app.extensions["smartlink"]
    state.config_manager.update_settings(
        {
            "api_token": "test-token",
            "listen_host": "127.0.0.1",
            "port": 5000,
            "allowed_networks": "127.0.0.1/32",
            "allowed_ips": "",
        }
    )
    state.config_manager.upsert_action(
        ActionConfig(
            name="打开记事本",
            type="exe",
            cmd="notepad.exe",
            category="办公",
            tags=["常用"],
            allow_api=True,
            enabled=True,
            favorite=True,
        )
    )
    state.config_manager.upsert_action(
        ActionConfig(
            name="私有动作",
            type="exe",
            cmd="calc.exe",
            category="办公",
            allow_api=False,
            enabled=True,
        )
    )
    state.config_manager.upsert_action(
        ActionConfig(
            name="亮度模板",
            type="brightness",
            cmd="brightness XXX",
            category="系统",
            allow_api=True,
            enabled=True,
        )
    )
    state.config_manager.upsert_action(
        ActionConfig(
            name="隐藏音乐动作",
            type="music",
            cmd="kugou://start.weixin",
            category="影音",
            allow_api=True,
            enabled=True,
        )
    )

    state.action_service.launcher.launch = lambda command: ExecutionResult(
        True,
        f"mock launch: {command}",
        {"command": command},
    )
    state.system_service.set_brightness = lambda value: ExecutionResult(
        True,
        f"亮度已设置为 {value}%",
        {"value": value},
    )
    state.paths.log_file.write_text(
        "\n".join(f"log line {index}" for index in range(80)),
        encoding="utf-8",
    )
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_headers():
    return {"X-SmartLink-Token": "test-token"}
