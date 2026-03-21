from __future__ import annotations

import ast
import json
import os
import shlex
import subprocess
import urllib.parse
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from smartlink.config import ConfigManager
from smartlink.models import (
    ACTION_TYPES,
    ActionConfig,
    AppSettings,
    ExecutionResult,
    TaskRecord,
    now_iso,
)
from smartlink.services.network import parse_lines

MUSIC_SCHEMES = {
    "网易云音乐": "ncm://start.weixin",
    "酷狗音乐": "kugou://start.weixin",
    "酷我音乐": "kuwo://start.weixin",
    "QQ 音乐": "qqmusic://start.weixin",
    "Apple Music": "applemusic://start.weixin",
}


class CommandLauncher:
    def launch(self, command_line: str) -> ExecutionResult:
        try:
            args = self._parse(command_line)
            subprocess.Popen(args, shell=False, **self._windows_process_kwargs())
        except (OSError, ValueError) as exc:
            return ExecutionResult(
                False, f"命令启动失败: {exc}", {"command": command_line}, "command_launch_failed"
            )
        return ExecutionResult(True, "命令已启动。", {"command": command_line})

    def _windows_process_kwargs(self) -> dict[str, Any]:
        if os.name != "nt":
            return {}
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        return {
            "creationflags": subprocess.CREATE_NO_WINDOW,
            "startupinfo": startupinfo,
        }

    def _parse(self, command_line: str) -> list[str]:
        line = command_line.strip()
        lowered = line.lower()
        if lowered.startswith("cmd /c "):
            return ["cmd.exe", "/c", line[7:]]
        if any(symbol in line for symbol in ("&&", "||", "|", ">", "<")):
            return ["cmd.exe", "/c", line]
        parts = shlex.split(line, posix=False)
        if not parts:
            raise ValueError("empty command")
        first = parts[0].lower()
        if first.endswith(".bat") or first.endswith(".cmd"):
            return ["cmd.exe", "/c", line]
        return parts


class ActionService:
    def __init__(
        self,
        config_manager: ConfigManager,
        adb_service,
        system_service,
        logger,
        launcher: CommandLauncher | None = None,
    ) -> None:
        self.config_manager = config_manager
        self.adb_service = adb_service
        self.system_service = system_service
        self.logger = logger
        self.launcher = launcher or CommandLauncher()
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="smartlink")
        self.task_history: deque[TaskRecord] = deque(maxlen=100)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def list_actions(self) -> list[ActionConfig]:
        return self.config_manager.list_actions()

    def get_recent_actions(self, limit: int = 6) -> list[ActionConfig]:
        actions = [item for item in self.list_actions() if item.last_run_at]
        return sorted(actions, key=lambda action: action.last_run_at, reverse=True)[:limit]

    def get_task_history(self, limit: int = 20) -> list[TaskRecord]:
        return list(self.task_history)[:limit]

    def validate_action(self, action: ActionConfig) -> list[str]:
        errors: list[str] = []
        if not action.name.strip():
            errors.append("动作名称不能为空。")
        if action.type not in ACTION_TYPES:
            errors.append(f"不支持的动作类型: {action.type}")
        if action.type in {"exe", "adb", "music"} and not action.cmd.strip():
            errors.append("当前动作类型必须填写命令或内容。")
        if action.type == "adb":
            for line in parse_lines(action.cmd):
                if not line.lower().startswith("adb "):
                    errors.append("ADB 动作的每一行都必须以 adb 开头。")
                    break
        if action.type == "brightness" and action.cmd and "XXX" not in action.cmd:
            errors.append("亮度动作命令模板必须包含 XXX 占位符。")
        return errors

    def action_from_payload(self, payload: dict[str, Any]) -> ActionConfig:
        return ActionConfig.from_dict(
            payload.get("name", "").strip(),
            {
                "type": payload.get("type", "exe"),
                "cmd": payload.get("cmd", ""),
                "uri_scheme": payload.get("uri_scheme", ""),
                "card_ids": payload.get("card_ids", ""),
                "bafy_topic": payload.get("bafy_topic", ""),
                "category": payload.get("category", "默认"),
                "tags": payload.get("tags", ""),
                "favorite": payload.get("favorite", False),
                "allow_api": payload.get("allow_api", False),
                "enabled": payload.get("enabled", False),
                "description": payload.get("description", ""),
                "run_count": payload.get("run_count", 0),
                "last_run_at": payload.get("last_run_at", ""),
                "last_result": payload.get("last_result"),
                "last_message": payload.get("last_message", ""),
            },
        )

    def save_action(
        self, payload: dict[str, Any], old_name: str = ""
    ) -> tuple[bool, list[str], ActionConfig]:
        action = self.action_from_payload(payload)
        errors = self.validate_action(action)
        if errors:
            return False, errors, action
        self.config_manager.upsert_action(action, old_name=old_name)
        return True, [], action

    def run_action_sync(
        self,
        name: str,
        brightness_value: int | None = None,
        source: str = "web",
        require_api_allowed: bool = False,
    ) -> ExecutionResult:
        action = self.config_manager.get_action(name)
        if action is None:
            return ExecutionResult(False, f"未找到动作: {name}", error="action_not_found")
        if not action.enabled:
            return ExecutionResult(False, f"动作已被禁用: {name}", error="action_disabled")
        if require_api_allowed and not action.allow_api:
            return ExecutionResult(False, f"动作未开放给 API: {name}", error="action_not_allowed")

        settings = self.config_manager.get_settings()
        result = self._execute(action, settings, brightness_value)
        self.config_manager.update_action_result(action.name, result.success, result.message)
        self.logger.info(
            "action_run source=%s name=%s success=%s message=%s",
            source,
            action.name,
            result.success,
            result.message,
        )
        return result

    def run_action_async(
        self,
        name: str,
        brightness_value: int | None = None,
        source: str = "background",
        require_api_allowed: bool = False,
    ) -> TaskRecord:
        task = TaskRecord(task_id=uuid.uuid4().hex[:12], source=source, action_name=name)
        self.task_history.appendleft(task)
        future = self.executor.submit(
            self.run_action_sync,
            name,
            brightness_value,
            source,
            require_api_allowed,
        )

        def _done_callback(done) -> None:
            try:
                result = done.result()
                task.status = "finished"
                task.finished_at = now_iso()
                task.success = result.success
                task.message = result.message
                task.error = result.error
            except Exception as exc:  # pragma: no cover
                task.status = "failed"
                task.finished_at = now_iso()
                task.success = False
                task.message = "后台执行异常。"
                task.error = str(exc)
                self.logger.exception("async action failed task=%s", task.task_id)

        future.add_done_callback(_done_callback)
        return task

    def _execute(
        self,
        action: ActionConfig,
        settings: AppSettings,
        brightness_value: int | None = None,
    ) -> ExecutionResult:
        if action.type == "exe":
            return self._run_exe_action(action)
        if action.type == "adb":
            if settings.adb_screen_on:
                self.adb_service.ensure_screen_on(settings)
            return self.adb_service.run_action_lines(action.cmd)
        if action.type == "music":
            if settings.music_screen_on:
                self.adb_service.ensure_screen_on(settings)
            return self._run_music_action(action)
        if action.type == "brightness":
            return self._run_brightness_action(action, brightness_value)
        return ExecutionResult(False, f"未知动作类型: {action.type}", error="unknown_action_type")

    def _run_exe_action(self, action: ActionConfig) -> ExecutionResult:
        last_result = ExecutionResult(True, "命令已执行。")
        for line in parse_lines(action.cmd):
            last_result = self.launcher.launch(line)
            if not last_result.success:
                return last_result
        return ExecutionResult(True, "EXE/脚本动作已启动。")

    def _run_music_action(self, action: ActionConfig) -> ExecutionResult:
        raw_cmd = action.cmd.strip()
        if raw_cmd.startswith(
            (
                "orpheus://",
                "ncm://",
                "qqmusic://",
                "kugou://",
                "kuwo://",
                "music://",
                "applemusic://",
            )
        ):
            final_uri = raw_cmd
        else:
            try:
                payload = json.loads(raw_cmd)
            except json.JSONDecodeError:
                payload = ast.literal_eval(raw_cmd)
            encoded = urllib.parse.quote(json.dumps(payload, ensure_ascii=False))
            final_uri = f"{action.uri_scheme or MUSIC_SCHEMES['酷狗音乐']}?{encoded}"
        return self.adb_service.open_uri(final_uri)

    def _run_brightness_action(
        self, action: ActionConfig, brightness_value: int | None
    ) -> ExecutionResult:
        value = 50 if brightness_value is None else brightness_value
        if not 0 <= value <= 100:
            return ExecutionResult(
                False, "亮度必须在 0 到 100 之间。", error="brightness_out_of_range"
            )
        if not action.cmd.strip():
            return self.system_service.set_brightness(value)
        rendered = action.cmd.replace("XXX", str(value))
        return self.launcher.launch(rendered)
