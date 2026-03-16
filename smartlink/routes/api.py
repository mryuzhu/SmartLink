from __future__ import annotations

from flask import Blueprint, jsonify, request

from smartlink.logging_utils import tail_log
from smartlink.runtime import get_state
from smartlink.services.network import get_client_ip, ip_allowed

api_bp = Blueprint("api", __name__)


def api_response(
    success: bool, message: str, data=None, error: str | None = None, status: int = 200
):
    return jsonify(
        {
            "success": success,
            "message": message,
            "data": data or {},
            "error": error,
        }
    ), status


def require_token():
    state = get_state()
    settings = state.config_manager.get_settings()
    token = request.headers.get("X-SmartLink-Token") or request.args.get("token", "")
    client_ip = get_client_ip(request)
    if token != settings.api_token:
        return api_response(False, "Token 无效。", error="unauthorized", status=401)
    if not ip_allowed(client_ip, settings):
        return api_response(False, "当前 IP 不在允许列表内。", error="ip_forbidden", status=403)
    return None


@api_bp.before_request
def before_api_request():
    failure = require_token()
    if failure is not None:
        return failure
    return None


@api_bp.get("/health")
def health():
    state = get_state()
    adb_status = state.adb_service.list_devices()
    integration_status = state.integration_manager.status()
    settings = state.config_manager.get_settings()
    last_task = state.action_service.get_task_history(limit=1)
    return api_response(
        True,
        "服务正常。",
        {
            "app": {
                "running": True,
                "started_at": state.started_at.astimezone().isoformat(timespec="seconds"),
                "host": settings.listen_host,
                "port": settings.port,
            },
            "adb": adb_status,
            "integrations": integration_status,
            "last_task": last_task[0].to_dict() if last_task else {},
        },
    )


@api_bp.get("/actions")
def actions():
    action_items = [
        {
            "name": action.name,
            "type": action.type,
            "category": action.category,
            "tags": action.tags,
            "favorite": action.favorite,
            "description": action.description,
            "allow_api": action.allow_api,
        }
        for action in get_state().action_service.list_actions()
        if action.allow_api and action.enabled
    ]
    return api_response(True, "已返回可用动作。", {"actions": action_items})


@api_bp.get("/logs")
def logs():
    state = get_state()
    logs_data = [line.rstrip("\n") for line in tail_log(state.paths.log_file, limit=50)]
    return api_response(True, "已返回最近日志。", {"logs": logs_data})


@api_bp.post("/run")
def run_action():
    payload = request.get_json(silent=True) or {}
    action_name = payload.get("action") or payload.get("name") or ""
    if not action_name:
        return api_response(False, "缺少 action 字段。", error="missing_action", status=400)
    brightness_value = payload.get("brightness_value")
    if brightness_value is not None:
        try:
            brightness_value = int(brightness_value)
        except (TypeError, ValueError):
            return api_response(
                False, "brightness_value 必须是整数。", error="invalid_brightness", status=400
            )
    result = get_state().action_service.run_action_sync(
        action_name,
        brightness_value=brightness_value,
        source="api",
        require_api_allowed=True,
    )
    return api_response(
        result.success, result.message, result.data, result.error, 200 if result.success else 400
    )


@api_bp.post("/run/<action_name>")
def run_action_by_name(action_name: str):
    payload = request.get_json(silent=True) or {}
    brightness_value = payload.get("brightness_value")
    if brightness_value is not None:
        try:
            brightness_value = int(brightness_value)
        except (TypeError, ValueError):
            return api_response(
                False, "brightness_value 必须是整数。", error="invalid_brightness", status=400
            )
    result = get_state().action_service.run_action_sync(
        action_name,
        brightness_value=brightness_value,
        source="api",
        require_api_allowed=True,
    )
    return api_response(
        result.success, result.message, result.data, result.error, 200 if result.success else 400
    )


@api_bp.post("/system/volume")
def api_volume():
    payload = request.get_json(silent=True) or {}
    try:
        value = int(payload.get("value"))
    except (TypeError, ValueError):
        return api_response(
            False, "value 必须是 0-100 的整数。", error="invalid_volume", status=400
        )
    if not 0 <= value <= 100:
        return api_response(
            False, "音量必须在 0 到 100 之间。", error="volume_out_of_range", status=400
        )
    result = get_state().system_service.set_volume(value)
    return api_response(
        result.success, result.message, result.data, result.error, 200 if result.success else 400
    )


@api_bp.post("/system/brightness")
def api_brightness():
    payload = request.get_json(silent=True) or {}
    try:
        value = int(payload.get("value"))
    except (TypeError, ValueError):
        return api_response(
            False, "value 必须是 0-100 的整数。", error="invalid_brightness", status=400
        )
    if not 0 <= value <= 100:
        return api_response(
            False,
            "亮度必须在 0 到 100 之间。",
            error="brightness_out_of_range",
            status=400,
        )
    result = get_state().system_service.set_brightness(value)
    return api_response(
        result.success, result.message, result.data, result.error, 200 if result.success else 400
    )


@api_bp.post("/system/shutdown")
def api_shutdown():
    result = get_state().system_service.shutdown()
    return api_response(result.success, result.message, result.data, result.error)


@api_bp.post("/system/restart")
def api_restart():
    result = get_state().system_service.restart()
    return api_response(result.success, result.message, result.data, result.error)


@api_bp.post("/system/lock")
def api_lock():
    result = get_state().system_service.lock()
    return api_response(
        result.success, result.message, result.data, result.error, 200 if result.success else 400
    )
