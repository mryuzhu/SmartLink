from __future__ import annotations

import ipaddress
import re
import shlex
import shutil
import subprocess
import time
from typing import Any

from smartlink.models import AppSettings, ExecutionResult
from smartlink.services.network import parse_lines


class ADBService:
    def __init__(self, logger) -> None:
        self.logger = logger

    def is_available(self) -> bool:
        return shutil.which("adb") is not None

    def validate_pair_ip(self, ip: str) -> bool:
        try:
            parsed = ipaddress.ip_address((ip or "").strip())
        except ValueError:
            return False
        return parsed.version == 4

    def validate_pair_port(self, port: str | int) -> bool:
        text = str(port).strip()
        return text.isdigit() and 1 <= int(text) <= 65535

    def validate_pair_code(self, code: str) -> bool:
        text = (code or "").strip()
        return bool(text) and text.isdigit()

    def build_pair_target(self, ip: str, port: str | int) -> str:
        return f"{ip.strip()}:{str(port).strip()}"

    def _run(self, args: list[str], timeout: int = 8) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            check=False,
        )

    def connect(self, ip: str) -> ExecutionResult:
        if not ip:
            return ExecutionResult(False, "未配置 ADB 设备地址。", error="missing_ip")
        if not self.is_available():
            return ExecutionResult(False, "未找到 adb，请先安装并加入 PATH。", error="adb_missing")
        result = self._run(["adb", "connect", ip], timeout=12)
        success = result.returncode == 0
        message = (result.stdout or result.stderr).strip() or (
            "连接成功。" if success else "连接失败。"
        )
        self.logger.info("adb_connect ip=%s success=%s message=%s", ip, success, message)
        return ExecutionResult(
            success, message, {"ip": ip}, None if success else "adb_connect_failed"
        )

    def pair(
        self,
        ip: str,
        pair_port: str | int,
        pair_code: str,
        debug_port: str | int | None = None,
    ) -> ExecutionResult:
        ip_text = (ip or "").strip()
        pair_port_text = str(pair_port).strip()
        pair_code_text = (pair_code or "").strip()
        debug_port_text = str(debug_port).strip() if debug_port not in (None, "") else "5555"

        if not self.validate_pair_ip(ip_text):
            return ExecutionResult(False, "设备 IP 无效。", error="invalid_pair_ip")
        if not self.validate_pair_port(pair_port_text):
            return ExecutionResult(False, "配对端口无效。", error="invalid_pair_port")
        if not self.validate_pair_code(pair_code_text):
            return ExecutionResult(False, "配对码无效。", error="invalid_pair_code")
        if not self.validate_pair_port(debug_port_text):
            return ExecutionResult(False, "调试端口无效。", error="invalid_debug_port")
        if not self.is_available():
            return ExecutionResult(False, "未找到 adb，请先安装并加入 PATH。", error="adb_missing")

        pair_target = self.build_pair_target(ip_text, pair_port_text)
        pair_result = self._run(["adb", "pair", pair_target, pair_code_text], timeout=15)
        pair_success = pair_result.returncode == 0
        pair_message = (pair_result.stdout or pair_result.stderr).strip() or (
            "配对成功。" if pair_success else "配对失败。"
        )
        self.logger.info(
            "adb_pair ip=%s port=%s success=%s message=%s",
            ip_text,
            pair_port_text,
            pair_success,
            pair_message,
        )
        if not pair_success:
            return ExecutionResult(
                False,
                pair_message,
                {"ip": ip_text, "pair_port": pair_port_text},
                "adb_pair_failed",
            )

        connect_target = self.build_pair_target(ip_text, debug_port_text)
        connect_result = self._run(["adb", "connect", connect_target], timeout=12)
        connect_success = connect_result.returncode == 0
        connect_message = (connect_result.stdout or connect_result.stderr).strip() or (
            "连接成功。" if connect_success else "连接失败。"
        )
        self.logger.info(
            "adb_connect ip=%s success=%s message=%s",
            connect_target,
            connect_success,
            connect_message,
        )
        if not connect_success:
            return ExecutionResult(
                False,
                f"{pair_message} {connect_message}".strip(),
                {
                    "ip": ip_text,
                    "pair_port": pair_port_text,
                    "debug_port": debug_port_text,
                },
                "adb_connect_failed",
            )
        return ExecutionResult(
            True,
            f"{pair_message} {connect_message}".strip(),
            {
                "ip": ip_text,
                "pair_port": pair_port_text,
                "debug_port": debug_port_text,
            },
        )

    def disconnect(self) -> ExecutionResult:
        if not self.is_available():
            return ExecutionResult(False, "未找到 adb，请先安装并加入 PATH。", error="adb_missing")
        result = self._run(["adb", "disconnect"], timeout=12)
        success = result.returncode == 0
        message = (result.stdout or result.stderr).strip() or (
            "已断开 ADB。" if success else "断开失败。"
        )
        self.logger.info("adb_disconnect success=%s message=%s", success, message)
        return ExecutionResult(success, message, {}, None if success else "adb_disconnect_failed")

    def list_devices(self) -> dict[str, Any]:
        if not self.is_available():
            return {"available": False, "connected": False, "devices": [], "raw": "adb not found"}
        result = self._run(["adb", "devices"], timeout=8)
        devices = []
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return {
            "available": True,
            "connected": bool(devices),
            "devices": devices,
            "raw": (result.stdout or result.stderr).strip(),
        }

    def is_screen_on(self) -> bool | None:
        if not self.is_available():
            return None
        result = self._run(["adb", "shell", "dumpsys", "display"], timeout=8)
        if result.returncode != 0:
            return None
        match = re.search(r"mState=(ON|OFF)", result.stdout)
        if not match:
            return None
        return match.group(1) == "ON"

    def ensure_screen_on(self, settings: AppSettings) -> None:
        if not self.is_available():
            return
        screen_on = self.is_screen_on()
        if screen_on is True:
            return
        subprocess.run(
            ["adb", "shell", "input", "keyevent", "KEYCODE_POWER"], check=False, timeout=8
        )
        time.sleep(1)
        if settings.unlock_after_screen_on and settings.device_password:
            subprocess.run(
                ["adb", "shell", "input", "text", settings.device_password],
                check=False,
                timeout=8,
            )
            time.sleep(1)

    def run_action_lines(self, command_text: str) -> ExecutionResult:
        if not self.is_available():
            return ExecutionResult(False, "未找到 adb，请先安装并加入 PATH。", error="adb_missing")
        lines = parse_lines(command_text)
        for line in lines:
            if not line.lower().startswith("adb "):
                return ExecutionResult(
                    False, f"ADB 动作只允许 adb 开头的命令: {line}", error="invalid_adb"
                )
            args = shlex.split(line, posix=False)
            result = self._run(args, timeout=15)
            if result.returncode != 0:
                message = (result.stderr or result.stdout).strip() or "ADB 命令执行失败。"
                self.logger.warning("ADB action failed line=%s message=%s", line, message)
                return ExecutionResult(False, message, {"command": line}, "adb_command_failed")
        return ExecutionResult(True, "ADB 命令已执行。")

    def open_uri(self, uri: str) -> ExecutionResult:
        if not self.is_available():
            return ExecutionResult(False, "未找到 adb，请先安装并加入 PATH。", error="adb_missing")
        result = self._run(
            ["adb", "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", uri],
            timeout=15,
        )
        success = result.returncode == 0
        message = (result.stdout or result.stderr).strip() or (
            "已发送 URI。" if success else "URI 打开失败。"
        )
        return ExecutionResult(
            success, message, {"uri": uri}, None if success else "adb_uri_failed"
        )

    def connect_if_needed(self, settings: AppSettings) -> None:
        if settings.enable_adb_connect and settings.adb_ip:
            self.connect(settings.adb_ip)
