from __future__ import annotations

import ipaddress
import os
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

    def validate_connect_target(self, target: str) -> bool:
        text = (target or "").strip()
        if not text:
            return False
        if ":" in text:
            host, _, port = text.rpartition(":")
            return self.validate_pair_ip(host) and self.validate_pair_port(port)
        return self.validate_pair_ip(text)

    def build_pair_target(self, ip: str, port: str | int) -> str:
        return f"{ip.strip()}:{str(port).strip()}"

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

    def _coerce_result(self, result: Any) -> ExecutionResult:
        if isinstance(result, ExecutionResult):
            return result
        stdout = getattr(result, "stdout", "") or ""
        stderr = getattr(result, "stderr", "") or ""
        returncode = getattr(result, "returncode", 1)
        message = "\n".join(item for item in [stdout.strip(), stderr.strip()] if item).strip()
        success = returncode == 0
        return ExecutionResult(
            success,
            message or ("ok" if success else "adb command failed"),
            {
                "stdout": stdout,
                "stderr": stderr,
                "returncode": returncode,
            },
            None if success else "adb_command_failed",
        )

    def _run(self, args: list[str], timeout: int = 5) -> ExecutionResult:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=timeout,
                check=False,
                **self._windows_process_kwargs(),
            )
        except subprocess.TimeoutExpired:
            command = " ".join(args)
            self.logger.error("adb timeout command=%s timeout=%s", command, timeout)
            return ExecutionResult(
                False,
                f"{args[0]} {args[1]} timeout" if len(args) > 1 else "adb timeout",
                {"command": command},
                "timeout",
            )
        except Exception as exc:  # pragma: no cover - defensive path
            command = " ".join(args)
            self.logger.error("adb command failed command=%s error=%s", command, exc)
            return ExecutionResult(
                False,
                f"adb command failed: {exc}",
                {"command": command},
                type(exc).__name__,
            )

        output = "\n".join(item for item in [result.stdout.strip(), result.stderr.strip()] if item).strip()
        success = result.returncode == 0
        return ExecutionResult(
            success,
            output or ("ok" if success else "adb command failed"),
            {
                "args": args,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            },
            None if success else "adb_command_failed",
        )

    def connect(self, ip: str) -> ExecutionResult:
        target = (ip or "").strip()
        if not target:
            return ExecutionResult(False, "未配置 ADB 设备地址。", error="missing_ip")
        if not self.validate_connect_target(target):
            return ExecutionResult(False, "ADB 设备地址格式无效。", {"ip": target}, "invalid_ip")
        if not self.is_available():
            return ExecutionResult(False, "未找到 adb，请先安装并加入 PATH。", error="adb_missing")

        result = self._run(["adb", "connect", target], timeout=5)
        success = result.success
        message = result.message or ("连接成功。" if success else "连接失败。")
        self.logger.info("adb_connect ip=%s success=%s message=%s", target, success, message)
        return ExecutionResult(success, message, {"ip": target, **result.data}, result.error)

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
        pair_result = self._coerce_result(
            self._run(["adb", "pair", pair_target, pair_code_text], timeout=5)
        )
        self.logger.info(
            "adb_pair ip=%s port=%s success=%s message=%s",
            ip_text,
            pair_port_text,
            pair_result.success,
            pair_result.message,
        )
        if not pair_result.success:
            return ExecutionResult(
                False,
                pair_result.message,
                {"ip": ip_text, "pair_port": pair_port_text, **pair_result.data},
                "adb_pair_failed",
            )

        connect_target = self.build_pair_target(ip_text, debug_port_text)
        connect_result = self._coerce_result(
            self._run(["adb", "connect", connect_target], timeout=5)
        )
        self.logger.info(
            "adb_connect ip=%s success=%s message=%s",
            connect_target,
            connect_result.success,
            connect_result.message,
        )
        if not connect_result.success:
            return ExecutionResult(
                False,
                f"{pair_result.message} {connect_result.message}".strip(),
                {
                    "ip": ip_text,
                    "pair_port": pair_port_text,
                    "debug_port": debug_port_text,
                    **connect_result.data,
                },
                "adb_connect_failed",
            )
        return ExecutionResult(
            True,
            f"{pair_result.message} {connect_result.message}".strip(),
            {
                "ip": ip_text,
                "pair_port": pair_port_text,
                "debug_port": debug_port_text,
                **connect_result.data,
            },
        )

    def disconnect(self) -> ExecutionResult:
        if not self.is_available():
            return ExecutionResult(False, "未找到 adb，请先安装并加入 PATH。", error="adb_missing")
        result = self._run(["adb", "disconnect"], timeout=5)
        self.logger.info(
            "adb_disconnect success=%s message=%s",
            result.success,
            result.message,
        )
        return ExecutionResult(result.success, result.message, result.data, result.error)

    def list_devices(self) -> dict[str, Any]:
        if not self.is_available():
            return {"available": False, "connected": False, "devices": [], "raw": "adb not found"}
        result = self._run(["adb", "devices"], timeout=5)
        output = (result.data.get("stdout") or result.data.get("stderr") or "").strip()
        devices: list[str] = []
        for line in output.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return {
            "available": True,
            "connected": bool(devices),
            "devices": devices,
            "raw": output,
        }

    def is_screen_on(self) -> bool | None:
        if not self.is_available():
            return None
        result = self._run(["adb", "shell", "dumpsys", "display"], timeout=5)
        if not result.success:
            return None
        stdout = result.data.get("stdout", "")
        match = re.search(r"mState=(ON|OFF)", stdout)
        if not match:
            return None
        return match.group(1) == "ON"

    def ensure_screen_on(self, settings: AppSettings) -> None:
        if not self.is_available():
            return
        screen_on = self.is_screen_on()
        if screen_on is True:
            return
        self._run(["adb", "shell", "input", "keyevent", "KEYCODE_POWER"], timeout=5)
        time.sleep(1)
        if settings.unlock_after_screen_on and settings.device_password:
            self._run(["adb", "shell", "input", "text", settings.device_password], timeout=5)
            time.sleep(1)

    def run_action_lines(self, command_text: str) -> ExecutionResult:
        if not self.is_available():
            return ExecutionResult(False, "未找到 adb，请先安装并加入 PATH。", error="adb_missing")
        lines = parse_lines(command_text)
        for line in lines:
            if not line.lower().startswith("adb "):
                return ExecutionResult(
                    False,
                    f"ADB 动作只允许 adb 开头的命令: {line}",
                    error="invalid_adb",
                )
            args = shlex.split(line, posix=False)
            result = self._run(args, timeout=5)
            if not result.success:
                self.logger.warning("ADB action failed line=%s message=%s", line, result.message)
                return ExecutionResult(False, result.message, {"command": line, **result.data}, result.error)
        return ExecutionResult(True, "ADB 命令已执行。")

    def open_uri(self, uri: str) -> ExecutionResult:
        if not self.is_available():
            return ExecutionResult(False, "未找到 adb，请先安装并加入 PATH。", error="adb_missing")
        result = self._run(
            ["adb", "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", uri],
            timeout=5,
        )
        return ExecutionResult(
            result.success,
            result.message,
            {"uri": uri, **result.data},
            result.error if not result.success else None,
        )

    def connect_if_needed(self, settings: AppSettings) -> ExecutionResult:
        if not settings.enable_adb_connect or not settings.adb_ip:
            return ExecutionResult(True, "ADB 自动连接未启用。")
        target = settings.adb_ip.strip()
        if not self.validate_connect_target(target):
            message = f"跳过 ADB 初始化，地址无效: {target}"
            self.logger.warning("adb_init skip reason=invalid_ip ip=%s", target)
            return ExecutionResult(False, message, {"ip": target}, "invalid_ip")
        if not self.is_available():
            message = "跳过 ADB 初始化，未找到 adb。"
            self.logger.warning("adb_init skip reason=adb_missing")
            return ExecutionResult(False, message, error="adb_missing")

        devices = self.list_devices()
        if target in devices["devices"]:
            message = f"ADB 已连接: {target}"
            self.logger.info("adb_init skip reason=already_connected ip=%s", target)
            return ExecutionResult(True, message, {"ip": target, "devices": devices["devices"]})

        last_result = ExecutionResult(False, "adb connect timeout", {"ip": target}, "adb_connect_failed")
        for attempt in range(1, 3):
            last_result = self.connect(target)
            if last_result.success:
                return last_result
            self.logger.warning(
                "adb_init retry=%s ip=%s message=%s",
                attempt,
                target,
                last_result.message,
            )
            if attempt < 2:
                time.sleep(2)
        return last_result
