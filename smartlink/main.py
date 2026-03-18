from __future__ import annotations

import argparse
import os
import threading
import time
import webbrowser

from werkzeug.serving import make_server

from smartlink import create_app
from smartlink.services.network import get_lan_addresses
from smartlink.services.tray import TrayManager, tray_available


def resolve_access_host(listen_host: str) -> str:
    """根据监听地址生成浏览器访问地址。"""
    normalized = (listen_host or "").strip()
    if normalized in {"", "0.0.0.0", "::"}:  # noqa: S104 - 这里仅比较配置，不做实际绑定
        return get_lan_addresses()[-1]
    return normalized


def start_adb_initializer(state, settings) -> threading.Thread:
    """后台初始化 ADB，避免阻塞 Web 启动。"""

    def _worker() -> None:
        time.sleep(2)
        state.logger.info("[SmartLink] adb init start")
        try:
            result = state.adb_service.connect_if_needed(settings)
            outcome = "done" if result.success else "failed"
            state.logger.info("[SmartLink] adb init %s message=%s", outcome, result.message)
        except Exception as exc:  # pragma: no cover - defensive path
            state.logger.error("[SmartLink] adb init failed error=%s", exc, exc_info=True)

    thread = threading.Thread(target=_worker, daemon=True, name="smartlink-adb-init")
    thread.start()
    return thread


class ServerThread(threading.Thread):
    def __init__(self, app, host: str, port: int) -> None:
        super().__init__(daemon=True)
        self.server = make_server(host, port, app, threaded=True)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self) -> None:
        self.server.serve_forever()

    def shutdown(self) -> None:
        self.server.shutdown()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SmartLink 控制台")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    parser.add_argument("--disable-tray", action="store_true", help="禁用系统托盘")
    parser.add_argument(
        "--config", default=os.getenv("SMARTLINK_CONFIG_FILE", ""), help="指定配置文件路径"
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    app = create_app(config_path=args.config or None)
    state = app.extensions["smartlink"]
    settings = state.config_manager.get_settings()
    state.integration_manager.start()

    host = settings.listen_host
    port = settings.port
    access_host = resolve_access_host(host)
    dashboard_url = f"http://{access_host}:{port}/"
    mobile_url = f"http://{access_host}:{port}/mobile"

    def maybe_open_browser() -> None:
        if not args.no_browser and settings.auto_open_browser:
            time.sleep(1.2)
            webbrowser.open(dashboard_url)

    threading.Thread(target=maybe_open_browser, daemon=True).start()
    state.logger.info("[SmartLink] starting...")
    state.logger.info("startup host=%s port=%s dashboard=%s", host, port, dashboard_url)

    if settings.tray_enabled and not args.disable_tray and tray_available():
        try:
            server = ServerThread(app, host, port)
            server.start()
        except OSError as exc:
            state.logger.error("service startup failed: %s", exc, exc_info=True)
            state.integration_manager.stop()
            state.action_service.shutdown()
            return 1

        state.logger.info("[SmartLink] web server ready")
        start_adb_initializer(state, settings)

        def _shutdown() -> None:
            state.integration_manager.stop()
            state.action_service.shutdown()
            server.shutdown()
            os._exit(0)

        try:
            TrayManager(dashboard_url=dashboard_url, mobile_url=mobile_url, on_exit=_shutdown).run()
            return 0
        except Exception as exc:  # pragma: no cover - tray env dependent
            state.logger.error("tray runtime error: %s", exc, exc_info=True)
            server.shutdown()
            state.integration_manager.stop()
            state.action_service.shutdown()
            return 1

    start_adb_initializer(state, settings)
    state.logger.info("[SmartLink] web server ready")
    try:
        app.run(host=host, port=port, threaded=True)
    except OSError as exc:
        state.logger.error("service startup failed: %s", exc, exc_info=True)
        return 1
    except Exception as exc:
        state.logger.error("service runtime error: %s", exc, exc_info=True)
        return 1
    finally:
        state.integration_manager.stop()
        state.action_service.shutdown()
    return 0
