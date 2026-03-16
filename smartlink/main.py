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
    state.adb_service.connect_if_needed(settings)
    state.integration_manager.start()

    host = settings.listen_host
    port = settings.port
    lan_host = get_lan_addresses()[-1]
    dashboard_url = f"http://{lan_host}:{port}/"
    mobile_url = f"http://{lan_host}:{port}/mobile"

    def maybe_open_browser() -> None:
        if not args.no_browser and settings.auto_open_browser:
            time.sleep(1.2)
            webbrowser.open(dashboard_url)

    threading.Thread(target=maybe_open_browser, daemon=True).start()

    if settings.tray_enabled and not args.disable_tray and tray_available():
        server = ServerThread(app, host, port)
        server.start()

        def _shutdown() -> None:
            state.integration_manager.stop()
            state.action_service.shutdown()
            server.shutdown()
            os._exit(0)

        TrayManager(dashboard_url=dashboard_url, mobile_url=mobile_url, on_exit=_shutdown).run()
        return 0

    try:
        app.run(host=host, port=port, threaded=True)
    except OSError as exc:
        state.logger.exception("服务启动失败: %s", exc)
        print(f"服务启动失败: {exc}")
        return 1
    finally:
        state.integration_manager.stop()
        state.action_service.shutdown()
    return 0
