from __future__ import annotations

import time
from pathlib import Path

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from smartlink.config import DEFAULT_CONFIG_PATH, PROJECT_ROOT, ConfigManager
from smartlink.logging_utils import setup_logging
from smartlink.routes.api import api_bp
from smartlink.routes.web import web_bp
from smartlink.runtime import AppPaths, AppState
from smartlink.services.actions import ActionService
from smartlink.services.adb import ADBService
from smartlink.services.integrations import IntegrationManager
from smartlink.services.network import get_client_ip
from smartlink.services.system_control import SystemService


def create_app(config_path: str | Path | None = None, testing: bool = False) -> Flask:
    root = PROJECT_ROOT
    config_file = Path(config_path or DEFAULT_CONFIG_PATH)
    log_file = root / "logs" / "smartlink.log"
    logger = setup_logging(log_file)
    config_manager = ConfigManager(config_file)
    adb_service = ADBService(logger)
    system_service = SystemService(logger)
    action_service = ActionService(config_manager, adb_service, system_service, logger)
    integration_manager = IntegrationManager(config_manager, action_service, logger)

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = "smartlink-console"
    app.json.ensure_ascii = False
    app.config["TESTING"] = testing

    state = AppState(
        paths=AppPaths(root=root, config_file=config_file, log_file=log_file),
        logger=logger,
        config_manager=config_manager,
        action_service=action_service,
        adb_service=adb_service,
        system_service=system_service,
        integration_manager=integration_manager,
    )
    app.extensions["smartlink"] = state

    @app.before_request
    def _before_request():
        request._started = time.perf_counter()

    @app.after_request
    def _after_request(response):
        duration_ms = round(
            (time.perf_counter() - getattr(request, "_started", time.perf_counter())) * 1000, 1
        )
        record = {
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "ip": get_client_ip(request),
            "duration_ms": duration_ms,
        }
        state.record_request(record)
        logger.info(
            "request method=%s path=%s status=%s ip=%s duration_ms=%s",
            request.method,
            request.path,
            response.status_code,
            record["ip"],
            duration_ms,
        )
        return response

    @app.errorhandler(Exception)
    def _handle_exception(exc):
        logger.exception("unhandled error path=%s", request.path)
        if request.path.startswith("/api/"):
            status = exc.code if isinstance(exc, HTTPException) else 500
            message = exc.description if isinstance(exc, HTTPException) else "服务内部错误。"
            return (
                jsonify(
                    {
                        "success": False,
                        "message": message,
                        "data": {},
                        "error": type(exc).__name__,
                    }
                ),
                status,
            )
        status = exc.code if isinstance(exc, HTTPException) else 500
        return f"页面处理失败：{exc}", status

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    return app
