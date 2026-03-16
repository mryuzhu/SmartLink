from __future__ import annotations

import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any

from smartlink.models import ActionConfig, AppSettings, now_iso

CONFIG_VERSION = 2
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = Path(
    os.getenv("SMARTLINK_CONFIG_FILE", str(PROJECT_ROOT / "config" / "launcher_config.json"))
)
LEGACY_CONFIG_PATH = Path.home() / "launcher_config.json"


def default_actions() -> list[ActionConfig]:
    return [
        ActionConfig(
            name="关机",
            type="exe",
            cmd="shutdown -s -t 60",
            category="系统",
            description="延时 60 秒关闭电脑",
            tags=["系统", "电源"],
        ),
        ActionConfig(
            name="设置亮度",
            type="brightness",
            cmd='WMIC /NAMESPACE:\\\\root\\wmi PATH WmiMonitorBrightnessMethods WHERE "Active=TRUE" CALL WmiSetBrightness Brightness=XXX Timeout=0',
            category="系统",
            description="设置主屏幕亮度，XXX 会被替换成 0-100。",
            tags=["系统", "亮度"],
        ),
    ]


class ConfigManager:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or DEFAULT_CONFIG_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cached: dict[str, Any] | None = None
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        if self.path.exists():
            self._cached = self._normalize(self._read_json(self.path))
            self._write_json(self._cached)
            return
        if LEGACY_CONFIG_PATH.exists():
            self._cached = self._normalize(self._read_json(LEGACY_CONFIG_PATH))
        else:
            self._cached = self._build_default_payload()
        self._write_json(self._cached)

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            broken = path.with_suffix(path.suffix + ".broken")
            path.replace(broken)
            return self._build_default_payload()
        except FileNotFoundError:
            return self._build_default_payload()

    def _write_json(self, payload: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_default_payload(self) -> dict[str, Any]:
        settings = AppSettings(api_token=secrets.token_hex(16))
        return {
            "version": CONFIG_VERSION,
            "settings": settings.to_dict(),
            "actions": [action.to_dict() for action in default_actions()],
        }

    def _normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "settings" in payload and "actions" in payload:
            settings = AppSettings.from_dict(payload.get("settings", {}))
            if not settings.api_token:
                settings.api_token = secrets.token_hex(16)
            actions = [
                ActionConfig.from_dict(item.get("name", ""), item)
                for item in payload.get("actions", [])
                if item.get("name")
            ]
        else:
            settings_dict: dict[str, Any] = {}
            actions = []
            legacy_key_map = {
                "_adb_ip": "adb_ip",
                "_serial_port": "serial_port",
                "_bafy_uid": "bafy_uid",
                "_enable_card_reader": "enable_card_reader",
                "_enable_adb_connect": "enable_adb_connect",
                "_music_screen_on": "music_screen_on",
                "_adb_screen_on": "adb_screen_on",
                "_unlock_after_screen_on": "unlock_after_screen_on",
                "_device_password": "device_password",
            }
            for key, value in payload.items():
                if key.startswith("_"):
                    settings_dict[legacy_key_map.get(key, key.removeprefix("_"))] = value
                else:
                    actions.append(ActionConfig.from_dict(key, value))
            settings = AppSettings.from_dict(settings_dict)
            if not settings.api_token:
                settings.api_token = secrets.token_hex(16)

        if not any(action.name == "关机" for action in actions):
            actions.insert(0, default_actions()[0])
        if not any(action.name == "设置亮度" for action in actions):
            actions.append(default_actions()[1])

        return {
            "version": CONFIG_VERSION,
            "settings": settings.to_dict(),
            "actions": [action.to_dict() for action in actions],
        }

    def load(self) -> dict[str, Any]:
        with self._lock:
            if self._cached is None:
                self._cached = self._normalize(self._read_json(self.path))
            return json.loads(json.dumps(self._cached))

    def save(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._cached = self._normalize(payload)
            self._write_json(self._cached)

    def get_settings(self) -> AppSettings:
        payload = self.load()
        settings = AppSettings.from_dict(payload["settings"])
        if os.getenv("SMARTLINK_HOST"):
            settings.listen_host = os.getenv("SMARTLINK_HOST", settings.listen_host)
        if os.getenv("SMARTLINK_PORT"):
            settings.port = int(os.getenv("SMARTLINK_PORT", settings.port))
        if os.getenv("SMARTLINK_API_TOKEN"):
            settings.api_token = os.getenv("SMARTLINK_API_TOKEN", settings.api_token)
        return settings

    def update_settings(self, settings_updates: dict[str, Any]) -> AppSettings:
        payload = self.load()
        current = AppSettings.from_dict(payload["settings"])
        updated = current.to_dict()
        updated.update(settings_updates)
        settings = AppSettings.from_dict(updated)
        if not settings.api_token:
            settings.api_token = current.api_token or secrets.token_hex(16)
        payload["settings"] = settings.to_dict()
        self.save(payload)
        return settings

    def list_actions(self) -> list[ActionConfig]:
        payload = self.load()
        actions = [
            ActionConfig.from_dict(item.get("name", ""), item)
            for item in payload["actions"]
            if item.get("name")
        ]
        return sorted(
            actions, key=lambda action: (not action.favorite, action.category, action.name.lower())
        )

    def get_action(self, name: str) -> ActionConfig | None:
        for action in self.list_actions():
            if action.name == name:
                return action
        return None

    def upsert_action(self, action: ActionConfig, old_name: str = "") -> None:
        payload = self.load()
        actions = [
            ActionConfig.from_dict(item.get("name", ""), item)
            for item in payload["actions"]
            if item.get("name")
        ]
        replaced = False
        target_names = {action.name}
        if old_name:
            target_names.add(old_name)
        normalized_actions = []
        for current in actions:
            if current.name in target_names and not replaced:
                normalized_actions.append(action)
                replaced = True
            elif current.name not in target_names:
                normalized_actions.append(current)
        if not replaced:
            normalized_actions.append(action)
        payload["actions"] = [item.to_dict() for item in normalized_actions]
        self.save(payload)

    def delete_actions(self, names: list[str]) -> int:
        payload = self.load()
        names_set = set(names)
        filtered = [item for item in payload["actions"] if item.get("name") not in names_set]
        deleted = len(payload["actions"]) - len(filtered)
        payload["actions"] = filtered
        self.save(payload)
        return deleted

    def export_payload(self, action_names: list[str] | None = None) -> dict[str, Any]:
        payload = self.load()
        if not action_names:
            return payload
        names_set = set(action_names)
        exported = dict(payload)
        exported["actions"] = [item for item in payload["actions"] if item.get("name") in names_set]
        return exported

    def import_payload(self, incoming: dict[str, Any], merge: bool = True) -> None:
        normalized = self._normalize(incoming)
        if not merge:
            self.save(normalized)
            return
        current = self.load()
        current_settings = AppSettings.from_dict(current["settings"]).to_dict()
        incoming_settings = AppSettings.from_dict(normalized["settings"]).to_dict()
        current_settings.update(
            {key: value for key, value in incoming_settings.items() if value not in ("", [])}
        )
        merged_actions = {
            item["name"]: ActionConfig.from_dict(item["name"], item)
            for item in current["actions"]
            if item.get("name")
        }
        for item in normalized["actions"]:
            if item.get("name"):
                merged_actions[item["name"]] = ActionConfig.from_dict(item["name"], item)
        merged_payload = {
            "version": CONFIG_VERSION,
            "settings": current_settings,
            "actions": [action.to_dict() for action in merged_actions.values()],
        }
        self.save(merged_payload)

    def update_action_result(self, name: str, success: bool, message: str) -> None:
        action = self.get_action(name)
        if action is None:
            return
        action.run_count += 1
        action.last_run_at = now_iso()
        action.last_result = success
        action.last_message = message
        self.upsert_action(action)
