from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

from smartlink.models import ExecutionResult

if sys.platform == "win32":
    import winreg
else:
    winreg = None


class SystemService:
    def __init__(self, logger) -> None:
        self.logger = logger

    def set_brightness(self, value: int) -> ExecutionResult:
        if not 0 <= value <= 100:
            return ExecutionResult(
                False, "亮度必须在 0 到 100 之间。", error="brightness_out_of_range"
            )
        if platform.system() != "Windows":
            return ExecutionResult(
                False, "当前仅内置 Windows 亮度控制。", error="brightness_unsupported"
            )
        powershell_cmd = (
            "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1,{value})"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", powershell_cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return ExecutionResult(True, f"亮度已设置为 {value}%。", {"value": value})
        fallback = subprocess.run(
            [
                "wmic",
                "/NAMESPACE:\\\\root\\wmi",
                "PATH",
                "WmiMonitorBrightnessMethods",
                "WHERE",
                "Active=TRUE",
                "CALL",
                "WmiSetBrightness",
                f"Brightness={value}",
                "Timeout=0",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
            check=False,
        )
        success = fallback.returncode == 0
        message = (fallback.stdout or fallback.stderr).strip() or (
            f"亮度已设置为 {value}%。" if success else "亮度设置失败。"
        )
        return ExecutionResult(
            success, message, {"value": value}, None if success else "brightness_failed"
        )

    def set_volume(self, value: int) -> ExecutionResult:
        if not 0 <= value <= 100:
            return ExecutionResult(False, "音量必须在 0 到 100 之间。", error="volume_out_of_range")
        nircmd = shutil.which("nircmd.exe")
        if not nircmd:
            return ExecutionResult(
                False,
                "当前未检测到 NirCmd，音量接口已预留但本机未启用。详见 SHORTCUTS_GUIDE.md。",
                error="volume_not_supported",
            )
        scaled = int((value / 100) * 65535)
        proc = subprocess.run(
            [nircmd, "setsysvolume", str(scaled)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=8,
            check=False,
        )
        success = proc.returncode == 0
        return ExecutionResult(
            success,
            f"系统音量已调整到 {value}%。" if success else "音量设置失败。",
            {"value": value},
            None if success else "volume_failed",
        )

    def shutdown(self) -> ExecutionResult:
        subprocess.Popen(["shutdown", "/s", "/t", "0"])
        return ExecutionResult(True, "已发送关机命令。")

    def restart(self) -> ExecutionResult:
        subprocess.Popen(["shutdown", "/r", "/t", "0"])
        return ExecutionResult(True, "已发送重启命令。")

    def lock(self) -> ExecutionResult:
        if platform.system() == "Windows":
            subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
            return ExecutionResult(True, "已锁定电脑。")
        return ExecutionResult(False, "当前仅内置 Windows 锁屏能力。", error="lock_unsupported")

    def set_startup(self, enabled: bool, command: str) -> ExecutionResult:
        if winreg is None:
            return ExecutionResult(
                False, "当前系统不支持开机自启配置。", error="startup_unsupported"
            )
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, "SmartLink", 0, winreg.REG_SZ, command)
                return ExecutionResult(True, "已启用开机自启。")
            try:
                winreg.DeleteValue(key, "SmartLink")
            except FileNotFoundError:
                pass
            return ExecutionResult(True, "已关闭开机自启。")

    def startup_command(self, project_root: Path) -> str:
        python_exe = Path(sys.executable)
        return f'"{python_exe}" "{project_root / "SmartLink.py"}" --no-browser'
