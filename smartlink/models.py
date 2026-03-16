from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

ACTION_TYPES = ("exe", "adb", "music", "brightness")


def now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def split_csv(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value).split(",")
    return [item.strip() for item in raw_items if item and str(item).strip()]


@dataclass(slots=True)
class ActionConfig:
    name: str
    type: str = "exe"
    cmd: str = ""
    uri_scheme: str = ""
    card_ids: list[str] = field(default_factory=list)
    bafy_topic: str = ""
    category: str = "默认"
    tags: list[str] = field(default_factory=list)
    favorite: bool = False
    allow_api: bool = True
    enabled: bool = True
    description: str = ""
    run_count: int = 0
    last_run_at: str = ""
    last_result: bool | None = None
    last_message: str = ""

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ActionConfig:
        return cls(
            name=name,
            type=str(data.get("type", "exe")).strip().lower() or "exe",
            cmd=str(data.get("cmd", "") or ""),
            uri_scheme=str(data.get("uri_scheme", "") or ""),
            card_ids=split_csv(data.get("card_ids") or data.get("card_id")),
            bafy_topic=str(data.get("bafy_topic", "") or ""),
            category=str(data.get("category", "默认") or "默认"),
            tags=split_csv(data.get("tags")),
            favorite=bool(data.get("favorite", False)),
            allow_api=bool(data.get("allow_api", True)),
            enabled=bool(data.get("enabled", True)),
            description=str(data.get("description", "") or ""),
            run_count=int(data.get("run_count", 0) or 0),
            last_run_at=str(data.get("last_run_at", "") or ""),
            last_result=data.get("last_result"),
            last_message=str(data.get("last_message", "") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "cmd": self.cmd,
            "uri_scheme": self.uri_scheme,
            "card_ids": self.card_ids,
            "bafy_topic": self.bafy_topic,
            "category": self.category,
            "tags": self.tags,
            "favorite": self.favorite,
            "allow_api": self.allow_api,
            "enabled": self.enabled,
            "description": self.description,
            "run_count": self.run_count,
            "last_run_at": self.last_run_at,
            "last_result": self.last_result,
            "last_message": self.last_message,
        }

    @property
    def card_id_text(self) -> str:
        return ", ".join(self.card_ids)

    @property
    def tags_text(self) -> str:
        return ", ".join(self.tags)


@dataclass(slots=True)
class AppSettings:
    listen_host: str = "127.0.0.1"
    port: int = 5000
    api_token: str = ""
    allowed_networks: list[str] = field(
        default_factory=lambda: ["127.0.0.1/32", "192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"]
    )
    allowed_ips: list[str] = field(default_factory=list)
    request_timeout: int = 15
    adb_ip: str = ""
    serial_port: str = "COM3"
    bafy_uid: str = ""
    enable_card_reader: bool = False
    enable_adb_connect: bool = False
    music_screen_on: bool = True
    adb_screen_on: bool = True
    unlock_after_screen_on: bool = False
    device_password: str = ""
    tray_enabled: bool = True
    auto_open_browser: bool = True
    show_windows_info_dialog: bool = False
    startup_enabled: bool = False
    ssh_host: str = ""
    ssh_user: str = ""
    ssh_port: int = 22

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSettings:
        return cls(
            listen_host=str(data.get("listen_host", "127.0.0.1") or "127.0.0.1"),
            port=int(data.get("port", 5000) or 5000),
            api_token=str(data.get("api_token", "") or ""),
            allowed_networks=split_csv(data.get("allowed_networks"))
            or ["127.0.0.1/32", "192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"],
            allowed_ips=split_csv(data.get("allowed_ips")),
            request_timeout=max(3, int(data.get("request_timeout", 15) or 15)),
            adb_ip=str(data.get("adb_ip", "") or ""),
            serial_port=str(data.get("serial_port", "COM3") or "COM3"),
            bafy_uid=str(data.get("bafy_uid", "") or ""),
            enable_card_reader=bool(data.get("enable_card_reader", False)),
            enable_adb_connect=bool(data.get("enable_adb_connect", False)),
            music_screen_on=bool(data.get("music_screen_on", True)),
            adb_screen_on=bool(data.get("adb_screen_on", True)),
            unlock_after_screen_on=bool(data.get("unlock_after_screen_on", False)),
            device_password=str(data.get("device_password", "") or ""),
            tray_enabled=bool(data.get("tray_enabled", True)),
            auto_open_browser=bool(data.get("auto_open_browser", True)),
            show_windows_info_dialog=bool(data.get("show_windows_info_dialog", False)),
            startup_enabled=bool(data.get("startup_enabled", False)),
            ssh_host=str(data.get("ssh_host", "") or ""),
            ssh_user=str(data.get("ssh_user", "") or ""),
            ssh_port=max(1, int(data.get("ssh_port", 22) or 22)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "listen_host": self.listen_host,
            "port": self.port,
            "api_token": self.api_token,
            "allowed_networks": self.allowed_networks,
            "allowed_ips": self.allowed_ips,
            "request_timeout": self.request_timeout,
            "adb_ip": self.adb_ip,
            "serial_port": self.serial_port,
            "bafy_uid": self.bafy_uid,
            "enable_card_reader": self.enable_card_reader,
            "enable_adb_connect": self.enable_adb_connect,
            "music_screen_on": self.music_screen_on,
            "adb_screen_on": self.adb_screen_on,
            "unlock_after_screen_on": self.unlock_after_screen_on,
            "device_password": self.device_password,
            "tray_enabled": self.tray_enabled,
            "auto_open_browser": self.auto_open_browser,
            "show_windows_info_dialog": self.show_windows_info_dialog,
            "startup_enabled": self.startup_enabled,
            "ssh_host": self.ssh_host,
            "ssh_user": self.ssh_user,
            "ssh_port": self.ssh_port,
        }

    @property
    def masked_token(self) -> str:
        if not self.api_token:
            return ""
        if len(self.api_token) <= 8:
            return "*" * len(self.api_token)
        return f"{self.api_token[:4]}...{self.api_token[-4:]}"


@dataclass(slots=True)
class ExecutionResult:
    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "error": self.error,
        }


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    source: str
    action_name: str
    status: str = "queued"
    created_at: str = field(default_factory=now_iso)
    finished_at: str = ""
    success: bool | None = None
    message: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "source": self.source,
            "action_name": self.action_name,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "success": self.success,
            "message": self.message,
            "error": self.error,
        }
