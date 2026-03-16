from __future__ import annotations

import base64
import io
import json

import qrcode
from flask import Blueprint, Response, flash, redirect, render_template, request, send_file, url_for

from smartlink.logging_utils import tail_log
from smartlink.runtime import get_state
from smartlink.services.network import get_lan_addresses

web_bp = Blueprint("web", __name__)


def _settings_from_form() -> dict:
    form = request.form
    return {
        "listen_host": form.get("listen_host", "127.0.0.1").strip() or "127.0.0.1",
        "port": int(form.get("port", "5000") or 5000),
        "api_token": form.get("api_token", "").strip(),
        "allowed_networks": form.get("allowed_networks", ""),
        "allowed_ips": form.get("allowed_ips", ""),
        "request_timeout": int(form.get("request_timeout", "15") or 15),
        "adb_ip": form.get("adb_ip", "").strip(),
        "serial_port": form.get("serial_port", "COM3").strip() or "COM3",
        "bafy_uid": form.get("bafy_uid", "").strip(),
        "enable_card_reader": bool(form.get("enable_card_reader")),
        "enable_adb_connect": bool(form.get("enable_adb_connect")),
        "music_screen_on": bool(form.get("music_screen_on")),
        "adb_screen_on": bool(form.get("adb_screen_on")),
        "unlock_after_screen_on": bool(form.get("unlock_after_screen_on")),
        "device_password": form.get("device_password", ""),
        "tray_enabled": bool(form.get("tray_enabled")),
        "auto_open_browser": bool(form.get("auto_open_browser")),
        "startup_enabled": bool(form.get("startup_enabled")),
        "ssh_host": form.get("ssh_host", "").strip(),
        "ssh_user": form.get("ssh_user", "").strip(),
        "ssh_port": int(form.get("ssh_port", "22") or 22),
    }


def _action_payload() -> dict:
    form = request.form
    return {
        "name": form.get("name", "").strip(),
        "type": form.get("type", "exe"),
        "cmd": form.get("cmd", ""),
        "uri_scheme": form.get("uri_scheme", ""),
        "card_ids": form.get("card_ids", ""),
        "bafy_topic": form.get("bafy_topic", ""),
        "category": form.get("category", "默认"),
        "tags": form.get("tags", ""),
        "favorite": bool(form.get("favorite")),
        "allow_api": bool(form.get("allow_api")),
        "enabled": bool(form.get("enabled")),
        "description": form.get("description", ""),
    }


def _qr_data_uri(url: str) -> str:
    image = qrcode.make(url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


@web_bp.get("/")
def dashboard():
    state = get_state()
    all_actions = [action for action in state.action_service.list_actions() if action.type != "music"]
    keyword = request.args.get("keyword", "").strip().lower()
    category = request.args.get("category", "").strip()
    actions = [
        action
        for action in all_actions
        if (not keyword or keyword in action.name.lower() or keyword in action.bafy_topic.lower())
        and (not category or action.category == category)
    ]
    settings = state.config_manager.get_settings()
    adb_status = state.adb_service.list_devices()
    categories = sorted({action.category for action in all_actions})
    recent_logs = [line.rstrip("\n") for line in tail_log(state.paths.log_file, limit=50)]
    task_history = [item.to_dict() for item in state.action_service.get_task_history()]
    favorite_actions = [
        item for item in all_actions if item.favorite and item.allow_api and item.enabled
    ]
    lan_addresses = get_lan_addresses()
    lan_host = lan_addresses[-1]
    mobile_url = f"http://{lan_host}:{settings.port}{url_for('web.mobile')}"
    api_base = f"http://{lan_host}:{settings.port}/api"
    preview_payload = state.config_manager.export_payload()
    preview_payload["actions"] = [
        item for item in preview_payload.get("actions", []) if item.get("type") != "music"
    ]
    config_preview = json.dumps(
        preview_payload,
        ensure_ascii=False,
        indent=2,
    )
    ssh_command = ""
    if settings.ssh_host and settings.ssh_user:
        ssh_command = (
            f"ssh -p {settings.ssh_port} {settings.ssh_user}@{settings.ssh_host} "
            '"powershell -Command \\"Invoke-RestMethod -Method Post '
            f"-Uri http://127.0.0.1:{settings.port}/api/run/关机 "
            f"-Headers @{{'X-SmartLink-Token'='{settings.api_token}'}}\\\"\""
        )
    return render_template(
        "dashboard.html",
        actions=actions,
        all_actions=all_actions,
        categories=categories,
        keyword=keyword,
        selected_category=category,
        settings=settings,
        adb_status=adb_status,
        integrations=state.integration_manager.status(),
        recent_logs=recent_logs,
        recent_actions=state.action_service.get_recent_actions(),
        task_history=task_history,
        request_history=list(state.request_history)[:20],
        api_base=api_base,
        mobile_url=mobile_url,
        config_preview=config_preview,
        qr_data_uri=_qr_data_uri(mobile_url),
        favorite_actions=favorite_actions,
        lan_addresses=lan_addresses,
        ssh_command=ssh_command,
        action_json={item.name: item.to_dict() for item in all_actions if item.type != "music"},
    )


@web_bp.post("/actions/save")
def save_action():
    state = get_state()
    ok, errors, action = state.action_service.save_action(
        _action_payload(), old_name=request.form.get("old_name", "").strip()
    )
    if not ok:
        for item in errors:
            flash(item, "error")
        return redirect(url_for("web.dashboard"))
    if request.form.get("run_after_save"):
        result = state.action_service.run_action_sync(action.name, source="web")
        flash(result.message, "success" if result.success else "error")
    else:
        flash(f"动作已保存：{action.name}", "success")
    return redirect(url_for("web.dashboard"))


@web_bp.post("/actions/<name>/delete")
def delete_action(name: str):
    deleted = get_state().config_manager.delete_actions([name])
    flash("动作已删除。" if deleted else "动作不存在。", "success" if deleted else "warning")
    return redirect(url_for("web.dashboard"))


@web_bp.post("/actions/bulk-delete")
def bulk_delete():
    names = request.form.getlist("selected_names")
    deleted = get_state().config_manager.delete_actions(names)
    flash(f"已删除 {deleted} 个动作。", "success")
    return redirect(url_for("web.dashboard"))


@web_bp.post("/actions/bulk-export")
def bulk_export():
    names = request.form.getlist("selected_names")
    payload = get_state().config_manager.export_payload(names or None)
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return send_file(
        io.BytesIO(content),
        as_attachment=True,
        download_name="smartlink-actions.json",
        mimetype="application/json",
    )


@web_bp.post("/actions/<name>/run")
def run_action(name: str):
    brightness_value = request.form.get("brightness_value")
    value = None
    if brightness_value not in (None, ""):
        try:
            value = int(brightness_value)
        except ValueError:
            flash("亮度值必须是整数。", "error")
            return redirect(url_for("web.dashboard"))
    result = get_state().action_service.run_action_sync(name, brightness_value=value, source="web")
    flash(result.message, "success" if result.success else "error")
    return redirect(url_for("web.dashboard"))


@web_bp.post("/settings/save")
def save_settings():
    state = get_state()
    settings = state.config_manager.update_settings(_settings_from_form())
    startup_result = state.system_service.set_startup(
        settings.startup_enabled,
        state.system_service.startup_command(state.paths.root),
    )
    flash("全局设置已保存，监听地址或端口变更需要重启程序。", "success")
    if startup_result.success:
        flash(startup_result.message, "success")
    return redirect(url_for("web.dashboard"))


@web_bp.post("/adb/connect")
def adb_connect():
    state = get_state()
    ip = request.form.get("ip") or state.config_manager.get_settings().adb_ip
    result = state.adb_service.connect(ip)
    flash(result.message, "success" if result.success else "error")
    return redirect(url_for("web.dashboard"))


@web_bp.post("/adb/pair")
def adb_pair():
    state = get_state()
    ip = request.form.get("pair_ip") or state.config_manager.get_settings().adb_ip
    pair_port = request.form.get("pair_port", "")
    pair_code = request.form.get("pair_code", "")
    debug_port = request.form.get("debug_port", "")
    result = state.adb_service.pair(ip, pair_port, pair_code, debug_port or None)
    flash(result.message, "success" if result.success else "error")
    return redirect(url_for("web.dashboard"))


@web_bp.post("/adb/disconnect")
def adb_disconnect():
    result = get_state().adb_service.disconnect()
    flash(result.message, "success" if result.success else "error")
    return redirect(url_for("web.dashboard"))


@web_bp.post("/config/import")
def import_config():
    upload = request.files.get("config_file")
    if upload is None or not upload.filename:
        flash("请选择要导入的 JSON 文件。", "error")
        return redirect(url_for("web.dashboard"))
    payload = json.loads(upload.read().decode("utf-8"))
    get_state().config_manager.import_payload(payload, merge=bool(request.form.get("merge_import")))
    flash("配置导入成功。", "success")
    return redirect(url_for("web.dashboard"))


@web_bp.get("/config/export")
def export_config():
    payload = get_state().config_manager.export_payload()
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return send_file(
        io.BytesIO(content),
        as_attachment=True,
        download_name="smartlink-config.json",
        mimetype="application/json",
    )


@web_bp.get("/logs")
def logs_text():
    state = get_state()
    return Response(
        state.paths.log_file.read_text(encoding="utf-8", errors="ignore"), mimetype="text/plain"
    )


@web_bp.get("/mobile")
def mobile():
    settings = get_state().config_manager.get_settings()
    actions = [
        action
        for action in get_state().action_service.list_actions()
        if action.type != "music" and action.allow_api and action.enabled and action.favorite
    ] or [
        action
        for action in get_state().action_service.list_actions()
        if action.type != "music" and action.allow_api and action.enabled
    ][:8]
    lan_host = get_lan_addresses()[-1]
    return render_template(
        "mobile.html",
        actions=actions,
        api_base=f"http://{lan_host}:{settings.port}/api",
        token_hint=settings.masked_token,
        guide_url=url_for("web.dashboard"),
    )
