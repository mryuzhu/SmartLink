# 依赖安装 + 打包 + 运行说明：
# 1. 安装依赖：pip install flask pyserial paho-mqtt pystray pillow
# 2. 打包为exe：pyinstaller -F SmartLink.py
# 3. 运行：双击 SmartLink.py 或命令行 python SmartLink.py
# 新增依赖：pystray pillow
# 打包提示：如需托盘图标请确保 icon.ico 文件存在于同目录，否则自动生成蓝底白字“SL”图标

import sys
import os
import json
import threading
import time
import subprocess
import webbrowser
import serial
import re
import urllib.parse
from flask import Flask, request, redirect, url_for, render_template_string, jsonify, flash

# 新增：系统托盘相关依赖
import io
import base64
try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    pystray = None
    Image = None

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

CONFIG_FILE = os.path.join(os.path.expanduser("~"), "launcher_config.json")

MUSIC_PLATFORMS = {
    "网易云音乐": "ncm://start.weixin",
    "酷狗音乐": "kugou://start.weixin",
    "酷我音乐": "kuwo://start.weixin",
    "QQ音乐": "qqmusic://start.weixin",
    "Apple Music": "applemusic://start.weixin"
}

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

def default_config(cfg):
    changed = False
    if "关机" not in cfg:
        cfg["关机"] = {
            "type": "exe",
            "cmd": "shutdown -s -t 60",
            "uri_scheme": "",
            "card_id": "",
            "bafy_topic": "off001"
        }
        changed = True
    if "设置亮度" not in cfg:
        cfg["设置亮度"] = {
            "type": "brightness",
            "cmd": 'WMIC /NAMESPACE:\\\\root\\wmi PATH WmiMonitorBrightnessMethods WHERE "Active=TRUE" CALL WmiSetBrightness Brightness=XXX Timeout=0',
            "uri_scheme": "",
            "card_id": "",
            "bafy_topic": "brightness002"
        }
        changed = True
    if "邓紫棋-喜欢你" not in cfg:
        cfg["邓紫棋-喜欢你"] = {
            "type": "music",
            "cmd": "{\n    \"cmd\": 212,\n    \"jsonStr\": {\n        \"bitrate\": 128,\n        \"duration\": 239,\n        \"extname\": \"mp3\",\n        \"filename\": \"G.E.M. 邓紫棋 - 喜欢你\",\n        \"hash\": \"cff4d61fa1318100ce18a88ebb52e335\"\n    }\n}",
            "uri_scheme": "kugou://start.weixin",
            "card_id": "",
            "bafy_topic": ""
        }
        changed = True
    if changed:
        save_config(cfg)
    return cfg

background_threads = []

def run_in_thread(fn, *args, **kwargs):
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()
    background_threads.append(t)
    return t

def start_card_reader_thread(cfg_getter, run_item_fn):
    def reader():
        while True:
            try:
                cfg = cfg_getter()
                serial_port = cfg.get("_serial_port", "COM3")
                enable_card = cfg.get("_enable_card_reader", True)
                if not enable_card:
                    time.sleep(1)
                    continue
                ser = serial.Serial(serial_port, 9600, timeout=1)
                while True:
                    data = ser.readline().decode(errors="ignore").strip()
                    if data:
                        for name, info in cfg.items():
                            if name.startswith("_"):
                                continue
                            card_ids = [x.strip() for x in info.get("card_id", "").split(",") if x.strip()]
                            if data in card_ids:
                                run_item_fn(name)
                                break
                    time.sleep(0.1)
            except Exception as e:
                print("读卡器线程异常:", e)
                time.sleep(5)
    run_in_thread(reader)

def start_bafy_mqtt_listener(cfg_getter, run_item_fn):
    if mqtt is None:
        print("paho-mqtt 未安装，MQTT监听不可用")
        return
    def mqtt_thread():
        while True:
            try:
                cfg = cfg_getter()
                topics = set()
                for name, info in cfg.items():
                    if name.startswith("_"):
                        continue
                    topic = info.get("bafy_topic")
                    if topic:
                        topics.add(topic)
                uid = cfg.get("_bafy_uid", "")
                if not uid or not topics:
                    time.sleep(5)
                    continue
                client = mqtt.Client(client_id=uid)
                def on_connect(client, userdata, flags, rc):
                    for t in topics:
                        client.subscribe(t)
                def on_message(client, userdata, msg):
                    payload = msg.payload.decode()
                    topic = msg.topic
                    for name, info in cfg.items():
                        if name.startswith("_"):
                            continue
                        if info.get("bafy_topic") == topic:
                            item_type = info.get("type", "").strip().lower()
                            if name == "关机" and payload == "off":
                                run_item_fn(name)
                            elif item_type in ["brightness", "value", "number"]:
                                try:
                                    value = None
                                    if payload.startswith("on#"):
                                        value = int(payload.split("#")[1])
                                    elif payload.isdigit():
                                        value = int(payload)
                                    if value is not None:
                                        run_item_fn(name, brightness_value=value)
                                except Exception:
                                    pass
                            elif name != "关机" and payload == "on":
                                run_item_fn(name)
                            break
                client.on_connect = on_connect
                client.on_message = on_message
                client.connect("bemfa.com", 9501, 60)
                client.loop_forever()
            except Exception as e:
                print("MQTT线程异常:", e)
                time.sleep(5)
    run_in_thread(mqtt_thread)

def is_screen_on():
    try:
        result = subprocess.run(
            ["adb", "shell", "dumpsys", "display"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        if result.returncode != 0:
            return None
        match = re.search(r'mState=(ON|OFF)', result.stdout)
        if not match:
            return None
        state = match.group(1)
        return state == "ON"
    except Exception:
        return None

def run_item(name, brightness_value=None, cfg=None):
    if cfg is None:
        cfg = load_config()
    info = cfg.get(name)
    if not info:
        return False, f"未找到启动项：{name}"
    item_type = info["type"].strip().lower()
    def try_screen_on():
        try:
            if is_screen_on() is not True:
                subprocess.Popen("adb shell input keyevent KEYCODE_POWER", shell=True)
                time.sleep(1)
                unlock = cfg.get("_unlock_after_screen_on", False)
                pwd = cfg.get("_device_password", "")
                if unlock and pwd:
                    subprocess.Popen(f'adb shell input text "{pwd}"', shell=True)
                    time.sleep(1)
        except Exception:
            subprocess.Popen("adb shell input keyevent KEYCODE_POWER", shell=True)
            time.sleep(1)
            unlock = cfg.get("_unlock_after_screen_on", False)
            pwd = cfg.get("_device_password", "")
            if unlock and pwd:
                subprocess.Popen(f'adb shell input text "{pwd}"', shell=True)
                time.sleep(1)
    if item_type == "exe":
        cmds = info["cmd"].splitlines()
        def run_cmds():
            for idx, cmd in enumerate(cmds):
                cmd = cmd.strip()
                if not cmd:
                    continue
                try:
                    subprocess.Popen(cmd, shell=True)
                except Exception as e:
                    print("命令执行失败:", e)
                if idx < len(cmds) - 1:
                    time.sleep(1)
        run_in_thread(run_cmds)
        return True, "已执行EXE命令"
    elif item_type == "adb":
        if cfg.get("_adb_screen_on", True):
            try_screen_on()
        cmds = info["cmd"].splitlines()
        def run_cmds():
            for idx, cmd in enumerate(cmds):
                cmd = cmd.strip()
                if not cmd:
                    continue
                try:
                    import shlex
                    if cmd.startswith("adb "):
                        cmd_list = shlex.split(cmd)
                        subprocess.Popen(cmd_list)
                    else:
                        subprocess.Popen(cmd, shell=True)
                except Exception as e:
                    print("命令执行失败:", e)
                if idx < len(cmds) - 1:
                    time.sleep(1)
        run_in_thread(run_cmds)
        return True, "已执行ADB命令"
    elif item_type == "music":
        if cfg.get("_music_screen_on", True):
            try_screen_on()
        try:
            cmd_data = info.get("cmd", "")
            if isinstance(cmd_data, str) and (cmd_data.startswith("orpheus://") or cmd_data.startswith("ncm://") or cmd_data.startswith("qqmusic://") or cmd_data.startswith("kugou://") or cmd_data.startswith("kuwo://") or cmd_data.startswith("music://")):
                final_uri = cmd_data
            else:
                if isinstance(cmd_data, str):
                    try:
                        music_json = json.loads(cmd_data)
                    except Exception:
                        music_json = eval(cmd_data)
                else:
                    music_json = cmd_data
                json_str = json.dumps(music_json, ensure_ascii=False)
                scheme = info.get("uri_scheme", "kugou://start.weixin")
                encoded_uri = urllib.parse.quote(json_str)
                final_uri = f'{scheme}?{encoded_uri}'
            adb_cmd = f'adb shell am start -a android.intent.action.VIEW -d "{final_uri}"'
            subprocess.Popen(adb_cmd, shell=True)
            return True, "已启动音乐"
        except Exception as e:
            return False, f"音乐启动失败：{e}"
    elif item_type == "brightness":
        cmd_template = info["cmd"]
        if brightness_value is not None:
            value = brightness_value
            ok = True
        else:
            value = 50
            ok = True
        if ok:
            cmd = cmd_template.replace("XXX", str(value))
            try:
                subprocess.Popen(cmd, shell=True)
                return True, "已设置亮度"
            except Exception as e:
                return False, f"亮度设置失败: {e}"
    return False, "未知类型"

app = Flask(__name__)
app.secret_key = "SmartLinkSecretKey"
app.config['JSON_AS_ASCII'] = False

@app.route("/", methods=["GET"])
def index():
    cfg = load_config()
    cfg = default_config(cfg)
    items = [(name, info) for name, info in cfg.items() if not name.startswith("_")]
    categories = set(info["type"] for name, info in items)
    query_type = request.args.get("type", "")
    keyword = request.args.get("kw", "").strip()
    filtered_items = items
    if query_type:
        filtered_items = [(n, i) for n, i in filtered_items if i["type"] == query_type]
    if keyword:
        # 支持按名称或巴法云 Topic 查询（不改变其他功能）
        kw = keyword.lower()
        filtered_items = [
            (n, i) for n, i in filtered_items
            if (kw in n.lower()) or (kw in (i.get("bafy_topic", "") or "").lower())
        ]
    settings = {
        "adb_ip": cfg.get("_adb_ip", ""),
        "serial_port": cfg.get("_serial_port", "COM3"),
        "bafy_uid": cfg.get("_bafy_uid", ""),
        "enable_card_reader": cfg.get("_enable_card_reader", True),
        "enable_adb_connect": cfg.get("_enable_adb_connect", True),
        "music_screen_on": cfg.get("_music_screen_on", True),
        "adb_screen_on": cfg.get("_adb_screen_on", True),
        "unlock_after_screen_on": cfg.get("_unlock_after_screen_on", False),
        "device_password": cfg.get("_device_password", "")
    }
    item_json_map = {n: json.dumps(i, ensure_ascii=False) for n, i in items}
    return render_template_string(PAGE_HTML,
        items=filtered_items,
        all_items=items,
        settings=settings,
        platforms=MUSIC_PLATFORMS,
        categories=categories,
        query_type=query_type,
        keyword=keyword,
        json=json,
        enumerate=enumerate,
        len=len,
        item_json_map=item_json_map
    )

@app.route("/save_item", methods=["POST"])
def save_item():
    cfg = load_config()
    old_name = request.form.get("old_name", "").strip()
    name = request.form.get("name", "").strip()
    info = {
        "type": request.form.get("type", "exe"),
        "cmd": request.form.get("cmd", ""),
        "uri_scheme": request.form.get("uri_scheme", ""),
        "card_id": request.form.get("card_id", ""),
        "bafy_topic": request.form.get("bafy_topic", "")
    }
    # 如果 old_name 存在且和新名字不同，则删除旧的启动项
    if old_name and old_name != name and old_name in cfg:
        del cfg[old_name]
    if not name:
        flash("名称不能为空")
        return redirect(url_for("index"))
    cfg[name] = info
    save_config(cfg)
    if request.form.get("run_after_save", "") == "1":
        run_item(name, cfg=cfg)
    flash(f"已保存启动项 {name}")
    return redirect(url_for("index"))

@app.route("/delete_item/<name>", methods=["POST"])
def delete_item(name):
    cfg = load_config()
    if name in cfg:
        cfg.pop(name)
        save_config(cfg)
        flash(f"已删除启动项 {name}")
    return redirect(url_for("index"))

@app.route("/run_item/<name>", methods=["POST"])
def run_item_api(name):
    value = request.form.get("brightness_value", None)
    if value is not None and value.isdigit():
        value = int(value)
    else:
        value = None
    ok, msg = run_item(name, brightness_value=value)
    flash(msg)
    return redirect(url_for("index"))

@app.route("/save_settings", methods=["POST"])
def save_settings():
    cfg = load_config()
    cfg["_adb_ip"] = request.form.get("adb_ip", "")
    cfg["_serial_port"] = request.form.get("serial_port", "COM3")
    cfg["_bafy_uid"] = request.form.get("bafy_uid", "")
    cfg["_enable_card_reader"] = bool(request.form.get("enable_card_reader"))
    cfg["_enable_adb_connect"] = bool(request.form.get("enable_adb_connect"))
    cfg["_music_screen_on"] = bool(request.form.get("music_screen_on"))
    cfg["_adb_screen_on"] = bool(request.form.get("adb_screen_on"))
    cfg["_unlock_after_screen_on"] = bool(request.form.get("unlock_after_screen_on"))
    cfg["_device_password"] = request.form.get("device_password", "")
    save_config(cfg)
    flash("已保存设置")
    return redirect(url_for("index"))

@app.route("/connect_adb", methods=["POST"])
def connect_adb():
    cfg = load_config()
    ip = cfg.get("_adb_ip", "")
    if ip:
        cmd = f'adb connect {ip}'
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="ignore")
            if result.returncode == 0:
                flash("连接成功: " + (result.stdout or result.stderr))
            else:
                flash("连接失败: " + (result.stderr or result.stdout))
        except Exception as e:
            flash(f"连接设备异常: {e}")
    else:
        flash("请先设置ADB设备IP")
    return redirect(url_for("index"))

@app.route("/disconnect_adb", methods=["POST"])
def disconnect_adb():
    try:
        result = subprocess.run("adb disconnect", shell=True, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if result.returncode == 0:
            flash("断开成功: " + (result.stdout or result.stderr))
        else:
            flash("断开失败: " + (result.stderr or result.stdout))
    except Exception as e:
        flash(f"断开设备异常: {e}")
    return redirect(url_for("index"))

@app.route("/parse_music", methods=["POST"])
def parse_music():
    text = request.form.get("music_link", "").strip()
    import re
    match = re.search(r'\?(.*)$', text)
    if not match:
        result = "未找到 ? 后的内容"
    else:
        encoded = match.group(1).strip()
        try:
            decoded = urllib.parse.unquote(encoded)
            decoded = decoded.replace('\\', '')
            try:
                obj = json.loads(decoded)
            except Exception:
                obj = eval(decoded)
            result = json.dumps(obj, ensure_ascii=False, indent=4)
        except Exception as e:
            result = f"解析失败: {e}"
    flash(result)
    return redirect(url_for("index"))

@app.route("/bafy/<cmd>", methods=["POST"])
def bafy_control(cmd):
    cfg = load_config()
    flash("请在启动项里设置Topic后刷卡/云端触发")
    return redirect(url_for("index"))

PAGE_HTML = '''
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <title>SmartLink 启动器 Web</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      :root{
        --sky-50: #f2fbff;
        --sky-100:#e6f8ff;
        --sky-200:#cdeffb;
        --sky-500:#1e90ff; /* 主天蓝色 */
        --muted:#6c7886;
        --card-bg:#ffffff;
        --glass: rgba(255,255,255,0.75);
        --text:#0f2333;
        --header-grad: linear-gradient(90deg,var(--sky-500), #4fb3ff);
      }

      /* 深色模式变量（通过 body.dark-mode 启用） */
      body.dark-mode {
        --sky-50: #0b0f12;
        --sky-100: #0f1417;
        --sky-200: #12181b;
        --sky-500: #9abcf7;
        --muted: #98a0a6;
        --card-bg: #0f1417;
        --glass: rgba(255,255,255,0.02);
        --text: #e6eef9;
        --header-grad: linear-gradient(90deg,#0f1720,#0b1220);
      }

      body{
        background: linear-gradient(180deg,var(--sky-50), #ffffff);
        padding:22px 16px;
        color:var(--text);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial;
      }
      body.dark-mode{
        background: linear-gradient(180deg,var(--sky-100), var(--sky-200));
      }

      .app-header{
        background: var(--header-grad);
        color:#fff;
        padding:12px 16px;
        border-radius:12px;
        box-shadow: 0 8px 30px rgba(30,144,255,0.08);
        margin-bottom:16px;
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
      }
      .app-title{ font-size:1.15rem; font-weight:800; letter-spacing:0.4px; }
      .app-sub{ font-size:0.82rem; opacity:0.95; margin-top:3px; }

      .header-right { display:flex; gap:8px; align-items:center; }

      .theme-btn{
        background: rgba(255,255,255,0.12);
        border: 1px solid rgba(255,255,255,0.12);
        color: #fff;
        padding:6px 10px;
        border-radius:8px;
        font-size:0.86rem;
      }
      .theme-btn:hover{ background: rgba(255,255,255,0.18); transform: translateY(-2px); }

      .main-row { display:flex; gap:20px; align-items:flex-start; }
      .main-left { flex:0 0 340px; min-width:300px; }
      .main-right { flex:1 1 0; }

      .card-panel{
        background:linear-gradient(180deg,var(--card-bg), #fbfeff);
        border-radius:12px;
        padding:12px;
        box-shadow: 0 6px 20px rgba(16,40,60,0.04);
        margin-bottom:14px;
        border: 1px solid rgba(30,144,255,0.04);
      }
      body.dark-mode .card-panel{
        background: linear-gradient(180deg,var(--card-bg), rgba(255,255,255,0.02));
        border-color: rgba(255,255,255,0.03);
        box-shadow: none;
      }

      .section-title { font-weight:800; color:var(--sky-500); margin-bottom:8px; font-size:1.02rem; }

      label{ font-weight:700; font-size:0.94rem; color:var(--text); }
      .form-control, .form-select { border-radius:8px; background:transparent; color:var(--text); border:1px solid rgba(30,144,255,0.06); }
      body.dark-mode .form-control, body.dark-mode .form-select { border:1px solid rgba(255,255,255,0.04); background: rgba(255,255,255,0.02); color:var(--text); }

      /* 全局按钮 hover 特效（淡淡泛白光 + 轻微放大） */
      .btn{
        transition: transform .14s ease, box-shadow .18s ease;
        position:relative;
        overflow:visible;
      }
      .btn:hover{
        transform: translateY(-2px) scale(1.01);
        box-shadow: 0 8px 20px rgba(30,144,255,0.10);
        z-index:3;
      }
      /* 泛白光更柔和、范围更小 */
      .btn::after{
        content: "";
        position: absolute;
        left: -30%;
        top: -40%;
        width: 20%;
        height: 180%;
        background: linear-gradient(120deg, rgba(255,255,255,0.0), rgba(255,255,255,0.14), rgba(255,255,255,0.0));
        transform: skewX(-20deg) translateX(-100%);
        transition: transform .6s ease;
        pointer-events:none;
        opacity:0.9;
      }
      .btn:hover::after{
        transform: skewX(-20deg) translateX(220%);
      }

      .btn-primary{ background:var(--sky-500); border-color:var(--sky-500); box-shadow:none; color:#fff; }
      .btn-connect { background:linear-gradient(90deg,#2b9bff,#1e90ff); border-color:transparent; color:#fff; }
      .btn-outline-primary{ color:var(--sky-500); border-color:rgba(30,144,255,0.18); background:transparent; }

      .item-grid { display:flex; flex-wrap:wrap; gap:16px; align-items:stretch; }
      /* 固定每张卡片大小，保证一致性 */
      .item-card { flex:1 1 280px; max-width:320px; min-width:260px; border-radius:12px; overflow:hidden; background:var(--card-bg); border:1px solid rgba(30,144,255,0.06); display:flex; }
      .item-card .card-body {
        padding:12px;
        display:flex;
        flex-direction:column;
        justify-content:space-between;
        width:100%;
        min-height:220px; /* 统一高度 */
        max-height:220px;
      }
      body.dark-mode .item-card { border-color: rgba(255,255,255,0.03); }

      .item-card .content { flex:1 1 auto; overflow:hidden; display:flex; flex-direction:column; gap:8px; }

      .actions { flex:0 0 auto; display:flex; justify-content:flex-end; gap:8px; align-items:center; margin-top:6px; }

      .badge-type { background: linear-gradient(90deg,#eaf8ff,#dff3ff); color:var(--sky-500); font-weight:700; border-radius:8px; padding:6px 10px; font-size:0.86rem; }

      /* 命令/秘密显示：限制行数，多余省略，hover 显示完整 title */
      .cmd-preview{
        color:#163d4f;
        font-size:0.86rem;
        line-height:1.18rem;
        display:-webkit-box;
        -webkit-line-clamp:4; /* 显示最多4行 */
        -webkit-box-orient:vertical;
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:normal;
        margin:2px 0;
      }
      body.dark-mode .cmd-preview { color:#dfefff; }

      .small-label{ color:var(--muted); font-size:0.86rem; margin-bottom:6px; display:block; }

      .tools-inline form{ display:inline-block; margin-right:8px; }

      .alert-info{ background:#eef8ff; border-color:rgba(30,144,255,0.06); color:var(--sky-500); }
      body.dark-mode .alert-info{ background: rgba(255,255,255,0.02); color:var(--muted); border-color: rgba(255,255,255,0.03); }

      @media (max-width:1000px){
        .main-row{ flex-direction:column; }
        .main-left, .main-right{ min-width:100%; flex:1 1 auto; }
        .item-card{ max-width:100%; min-width:auto; flex:1 1 100%; }
        .item-card .card-body { min-height:180px; max-height:unset; }
      }
    </style>
  </head>
  <body>
    <div class="container-fluid">
      <div class="app-header">
        <div>
          <div class="app-title">SmartLink 启动器 Web</div>
          <div class="app-sub">在浏览器中管理启动项 · 天蓝 & 白色调</div>
        </div>

        <div class="header-right">
          <div style="text-align:right; font-size:0.9rem; opacity:0.95; color:rgba(255,255,255,0.95);">Web 控制面板</div>
          <button id="theme-toggle-btn" class="theme-btn" title="切换深色/浅色模式">切换主题</button>
        </div>
      </div>

      {% with messages = get_flashed_messages() %}
        {% if messages %}
        <div class="alert alert-info">{{ messages|join('<br>')|safe }}</div>
        {% endif %}
      {% endwith %}

      <div class="main-row">
        <div class="main-left">
          <!-- 添加/编辑启动项 -->
          <div class="card-panel">
            <div class="section-title">添加 / 编辑 启动项</div>
            <form method="POST" action="{{ url_for('save_item') }}" id="editForm">
              <input type="hidden" name="old_name" id="old_name">
              <div class="mb-2">
                <label>名称</label>
                <input type="text" class="form-control" name="name" id="item_name" required>
              </div>
              <div class="mb-2">
                <label>类型</label>
                <select class="form-select" name="type" id="item_type" onchange="toggleFields()">
                  <option value="exe">exe</option>
                  <option value="adb">adb</option>
                  <option value="music">music</option>
                  <option value="brightness">brightness</option>
                </select>
              </div>
              <div class="mb-2">
                <label>音乐平台协议（music类型填）</label>
                <input type="text" class="form-control" name="uri_scheme" id="item_uri_scheme" placeholder="如 kugou://start.weixin">
              </div>
              <div class="mb-2">
                <label>巴法云Topic</label>
                <input type="text" class="form-control" name="bafy_topic" id="item_bafy_topic">
              </div>
              <div class="mb-2">
                <label>路径 / 命令 / 音乐JSON</label>
                <textarea class="form-control" name="cmd" id="item_cmd" rows="3"></textarea>
              </div>
              <div class="mb-2">
                <label>绑定卡号</label>
                <input type="text" class="form-control" name="card_id" id="item_card_id" placeholder="多个用英文逗号分隔">
              </div>
              <div class="form-check mb-2">
                <input type="checkbox" name="run_after_save" value="1" id="run_after_save" class="form-check-input">
                <label class="form-check-label" for="run_after_save">保存后立即运行</label>
              </div>
              <button class="btn btn-primary w-100" type="submit">保存启动项</button>
            </form>
          </div>

          <!-- 全局设置 -->
          <div class="card-panel">
            <div class="section-title">全局设置</div>
            <ul class="nav nav-tabs mb-3" id="settingsTabs" role="tablist">
              <li class="nav-item" role="presentation">
                <button class="nav-link active" id="device-tab" data-bs-toggle="tab" data-bs-target="#device" type="button" role="tab">设备 / ADB</button>
              </li>
              <li class="nav-item" role="presentation">
                <button class="nav-link" id="card-tab" data-bs-toggle="tab" data-bs-target="#card" type="button" role="tab">读卡器 / 巴法云</button>
              </li>
            </ul>
            <form method="POST" action="{{ url_for('save_settings') }}">
              <div class="tab-content" id="settingsTabsContent">
                <div class="tab-pane fade show active" id="device" role="tabpanel">
                  <div class="mb-2">
                    <label>ADB设备IP</label>
                    <input type="text" class="form-control" name="adb_ip" value="{{ settings.adb_ip }}">
                  </div>
                  <div class="form-check mb-2">
                    <input type="checkbox" class="form-check-input" name="enable_adb_connect" {% if settings.enable_adb_connect %}checked{% endif %}>
                    <label class="form-check-label">启动时ADB连接</label>
                  </div>
                  <div class="form-check mb-2">
                    <input type="checkbox" class="form-check-input" name="adb_screen_on" {% if settings.adb_screen_on %}checked{% endif %}>
                    <label class="form-check-label">ADB前亮屏</label>
                  </div>
                  <div class="form-check mb-2">
                    <input type="checkbox" class="form-check-input" name="music_screen_on" {% if settings.music_screen_on %}checked{% endif %}>
                    <label class="form-check-label">音乐前亮屏</label>
                  </div>
                  <div class="form-check mb-2">
                    <input type="checkbox" class="form-check-input" name="unlock_after_screen_on" {% if settings.unlock_after_screen_on %}checked{% endif %}>
                    <label class="form-check-label">亮屏后解锁</label>
                  </div>
                  <div class="mb-2">
                    <label>设备解锁密码</label>
                    <input type="password" class="form-control" name="device_password" value="{{ settings.device_password }}">
                  </div>
                  <div class="d-flex gap-2">
                    <button class="btn btn-connect btn-sm flex-grow-1" type="button" id="connect-adb-btn">连接设备</button>
                    <button class="btn btn-outline-primary btn-sm flex-grow-1" type="button" id="disconnect-adb-btn">断开连接</button>
                  </div>
                </div>

                <div class="tab-pane fade" id="card" role="tabpanel">
                  <div class="mb-2">
                    <label>读卡器串口号</label>
                    <input type="text" class="form-control" name="serial_port" value="{{ settings.serial_port }}">
                  </div>
                  <div class="form-check mb-2">
                    <input type="checkbox" class="form-check-input" name="enable_card_reader" {% if settings.enable_card_reader %}checked{% endif %}>
                    <label class="form-check-label">启用读卡器</label>
                  </div>
                  <div class="mb-2">
                    <label>巴法云UID</label>
                    <input type="text" class="form-control" name="bafy_uid" value="{{ settings.bafy_uid }}">
                  </div>
                </div>
              </div>
              <button class="btn btn-secondary w-100 mt-2" type="submit">保存设置</button>
            </form>
          </div>

          <!-- 辅助工具 -->
          <div class="card-panel">
            <div class="section-title">工具</div>
            <form method="POST" action="{{ url_for('parse_music') }}">
              <label>音乐链接解析</label>
              <input type="text" class="form-control mb-2" name="music_link" placeholder="输入音乐启动链接（如 kugou://start.weixin?...）">
              <button class="btn btn-primary w-100" type="submit">解析链接</button>
            </form>

            <div class="mt-3">
              <label class="d-block mb-2">巴法云云端按钮（请在启动项设置Topic后使用）</label>
              <div class="tools-inline">
                <form method="POST" action="{{ url_for('bafy_control', cmd='on') }}">
                  <button class="btn btn-primary me-2" type="submit">发送开</button>
                </form>
                <form method="POST" action="{{ url_for('bafy_control', cmd='off') }}">
                  <button class="btn btn-primary" type="submit">发送关</button>
                </form>
              </div>
            </div>
          </div>
        </div>

        <div class="main-right">
          <div class="section-title mb-3">启动项列表</div>

          <form class="d-flex mb-3 gap-2" method="GET" action="{{ url_for('index') }}">
            <select name="type" class="form-select form-select-sm" style="width:150px;" onchange="this.form.submit()">
              <option value="" {% if not query_type %}selected{% endif %}>全部类型</option>
              {% for cat in categories %}
                <option value="{{ cat }}" {% if query_type==cat %}selected{% endif %}>{{ cat }}</option>
              {% endfor %}
            </select>
            <input type="text" name="kw" class="form-control form-control-sm" style="width:260px;" placeholder="名称或Topic查询" value="{{ keyword }}">
            <button class="btn btn-outline-primary btn-sm" type="submit">查询</button>
            <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('index') }}">重置</a>
          </form>

          <div class="item-grid">
            {% if len(items)==0 %}
              <div class="alert alert-warning w-100">没有匹配启动项。</div>
            {% endif %}
            {% for idx, (name, info) in enumerate(items) %}
              <div class="item-card">
                <div class="card-body">
                  <div class="content">
                    <div class="d-flex justify-content-between align-items-start">
                      <div style="min-width:0;">
                        <div style="display:flex; gap:8px; align-items:center;">
                          <span class="badge-type">{{ info.type }}</span>
                          <div style="font-weight:800; font-size:1rem; color:var(--text); max-width:160px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="{{ name }}">{{ name }}</div>
                        </div>
                        <div class="small-label mt-2">协议: <span class="text-primary">{{ info.uri_scheme }}</span></div>
                      </div>
                      <div style="text-align:right; min-width:110px;">
                        <div class="small-label">卡号: <span class="text-success">{{ info.card_id }}</span></div>
                        <div class="small-label">Topic: <span class="text-success" title="{{ info.bafy_topic }}">{{ info.bafy_topic }}</span></div>
                      </div>
                    </div>

                    <div class="mt-2">
                      <div class="small-label">命令/JSON:</div>
                      <div class="cmd-preview" title="{{ info.cmd|e }}">{{ info.cmd }}</div>
                    </div>
                  </div>

                  <div class="actions">
                    <form method="POST" action="{{ url_for('run_item_api', name=name) }}" style="display:inline-flex; align-items:center;">
                      {% if info.type == "brightness" %}
                        <input type="number" name="brightness_value" min="0" max="100" value="50" class="form-control form-control-sm me-2" style="width:90px;" required>
                      {% endif %}
                      <button class="btn btn-primary btn-sm" type="submit">运行</button>
                    </form>

                    <button class="btn btn-primary btn-sm edit-btn" type="button" data-name="{{ name }}">编辑</button>

                    <form method="POST" action="{{ url_for('delete_item', name=name) }}" style="display:inline;" onsubmit="return confirm('确定删除 {{ name }}?');">
                      <button class="btn btn-outline-danger btn-sm" type="submit">删除</button>
                    </form>
                  </div>

                </div>
              </div>
            {% endfor %}
          </div>
        </div>
      </div>

      <div class="text-center mt-4" style="color:var(--muted);">SmartLink Web © 2025 mryuzhu</div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
      // 主题切换（深色/浅色） — 右上按钮
      (function(){
        var btn = document.getElementById('theme-toggle-btn');
        function applyTheme(t){
          if(t === 'dark'){ document.body.classList.add('dark-mode'); btn.textContent = '切换到浅色'; }
          else { document.body.classList.remove('dark-mode'); btn.textContent = '切换到深色'; }
        }
        var saved = localStorage.getItem('smartlink_theme') || 'light';
        applyTheme(saved);
        btn.addEventListener('click', function(){
          var cur = document.body.classList.contains('dark-mode') ? 'dark' : 'light';
          var next = cur === 'dark' ? 'light' : 'dark';
          localStorage.setItem('smartlink_theme', next);
          applyTheme(next);
        });
      })();

      // 编辑按钮事件：填充左侧表单（未改动逻辑）
      document.querySelectorAll(".edit-btn").forEach(function(btn){
        btn.onclick = function(){
          var name = btn.getAttribute("data-name");
          var map = {{ item_json_map|tojson }};
          if(map[name]){
            var info = JSON.parse(map[name]);
            document.getElementById("item_name").value = name;
            document.getElementById("item_type").value = info.type || "exe";
            document.getElementById("item_uri_scheme").value = info.uri_scheme || "";
            document.getElementById("item_cmd").value = info.cmd || "";
            document.getElementById("item_card_id").value = info.card_id || "";
            document.getElementById("item_bafy_topic").value = info.bafy_topic || "";
            document.getElementById("item_name").focus();
            toggleFields();
          }
        }
      });
      function toggleFields() {
        var type = document.getElementById("item_type").value;
        document.getElementById("item_uri_scheme").disabled = type !== "music";
      }
      document.getElementById("item_type").addEventListener("change", toggleFields);
      toggleFields();
      if(window.location.hash=="#edit"){document.getElementById("item_name").focus();}

      // 连接设备与断开设备（保持原有异步接口）
      document.getElementById("connect-adb-btn")?.addEventListener("click", function(){
        var ip = document.querySelector("input[name='adb_ip']").value;
        fetch("/adb_action/connect", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ip: ip })
        }).then(r => r.json()).then(data => alert(data.msg));
      });
      document.getElementById("disconnect-adb-btn")?.addEventListener("click", function(){
        fetch("/adb_action/disconnect", { method: "POST" }).then(r => r.json()).then(data => alert(data.msg));
      });
    </script>
  </body>
</html>
'''

# 新增：ADB连接/断开接口
@app.route("/adb_action/<action>", methods=["POST"])
def adb_action(action):
    msg = ""
    if action == "connect":
        data = request.get_json(force=True)
        ip = data.get("ip", "")
        if ip:
            try:
                result = subprocess.run(f"adb connect {ip}", shell=True, capture_output=True, text=True)
                msg = result.stdout.strip() or result.stderr.strip()
                if result.returncode == 0:
                    msg = "连接成功：" + msg
                else:
                    msg = "连接失败：" + msg
            except Exception as e:
                msg = f"错误：{e}"
        else:
            msg = "请输入设备IP"
    elif action == "disconnect":
        try:
            result = subprocess.run("adb disconnect", shell=True, capture_output=True, text=True)
            msg = result.stdout.strip() or result.stderr.strip()
            if result.returncode == 0:
                msg = "已断开：" + msg
            else:
                msg = "断开失败：" + msg
        except Exception as e:
            msg = f"错误：{e}"
    else:
        msg = "未知操作"
    return jsonify({ "msg": msg })

def connect_device_if_needed():
    cfg = load_config()
    if cfg.get("_enable_adb_connect", True):
        ip = cfg.get("_adb_ip", "")
        if ip:
            cmd = f'adb connect {ip}'
            try:
                subprocess.run(cmd, shell=True)
            except Exception as e:
                print("ADB连接失败:", e)

# 新增：帮助文本
HELP_TEXT = """SmartLink Web 启动器
用法:
    SmartLink.exe                启动并自动打开浏览器
    SmartLink.exe --no-browser   后台运行，不自动打开浏览器
    SmartLink.exe -help          显示本帮助文本
"""

# 新增：托盘图标生成函数
def get_tray_icon():
    icon_path = os.path.join(os.path.dirname(sys.argv[0]), "icon.ico")
    if os.path.exists(icon_path):
        try:
            return Image.open(icon_path)
        except Exception:
            pass
    # 自动生成蓝底白字“SL”图标
    img = Image.new("RGBA", (32, 32), (30, 144, 255, 255))  # 天蓝色底
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    text = "SL"
    # 修正：用 textbbox 获取宽高
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text(((32-w)//2, (32-h)//2), text, font=font, fill=(255,255,255,255))
    return img

# 新增：托盘主逻辑
class TrayManager:
    def __init__(self, app_quit_callback):
        self.icon = None
        self.thread = None
        self.app_quit_callback = app_quit_callback
        self._stop_event = threading.Event()

    def _on_open(self, icon, item):
        webbrowser.open("http://127.0.0.1:5000")

    def _on_exit(self, icon, item):
        self._stop_event.set()
        if self.icon:
            self.icon.stop()
        self.app_quit_callback()

    def run(self):
        if pystray is None or Image is None:
            print("未安装 pystray/pillow，托盘功能不可用")
            return
        image = get_tray_icon()
        menu = pystray.Menu(
            pystray.MenuItem("打开 Web 设置", self._on_open),
            pystray.MenuItem("退出程序", self._on_exit)
        )
        self.icon = pystray.Icon("SmartLink", image, "SmartLink 启动器", menu)
        self.icon.run()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self._stop_event.set()
        if self.icon:
            self.icon.stop()

# 新增：安全退出逻辑
def safe_exit():
    # 关闭 Flask（略，Flask主线程退出即可）
    # 关闭所有后台线程
    os._exit(0)

def run_flask():
    app.run(host="127.0.0.1", port=5000, threaded=True)

if __name__ == "__main__":
    # 参数解析
    args = sys.argv[1:]
    if any(a in args for a in ["-help", "--help"]):
        print(HELP_TEXT)
        sys.exit(0)

    no_browser = any(a in args for a in ["--no-browser", "-no-browser"])

    cfg = load_config()
    cfg = default_config(cfg)
    connect_device_if_needed()
    start_card_reader_thread(load_config, run_item)
    start_bafy_mqtt_listener(load_config, run_item)

    # 启动 Flask 后台线程
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # 自动打开浏览器（除非 --no-browser 参数）
    if not no_browser:
        threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:5000")).start()

    # 托盘必须在主线程运行
    tray_mgr = TrayManager(app_quit_callback=safe_exit)
    tray_mgr.run()  # 不用 .start()，直接主线程运行